"""
Tektronix 306B RSA API Wrapper

This file wraps the Python/Ctypes RSA API, with the goal of making
further development in Python more streamlined and intuitive. It
implements a majority of the RSA API functions for the 306B. Some API
documentation is included in docstrings, however this is mostly for
quick reference during development, and is not a substitute for the
full RSA API reference manual.

Input type checking and error handling have been implemented.
ValueError's and TypeError's are thrown where applicable, and
RSA_Error's are thrown for errors which relate to the unique
implementation of certain API calls. Additionally, errors which
occur when running the function on the device are passed back through
to RSA_Error.

This file requires the libRSA_API.so and libcyusb_shared.so files from
the Tektronix RSA API, and expects to find them in ./drivers/ relative
to the location of this file.

Note that the following API functions are not implemented:
- Any functions which do not apply to the 306B
- All DPX functions
- All IFSTREAM functions
- All PLAYBACK functions
- DEVICE_GetErrorString()
    - Alternate error handling is used.
- DEVICE_GetNomenclatureW()
    - DEVICE_GetNomenclature() is used instead.
- IQBLK_GetIQDataCplx()
    - IQBLK_GetIQData(), IQBLK_GetIQDataDeinterleaved are used instead.
- IQSTREAM_GetIQData()
    - IQSTREAM_Tempfile() likely does what you need.
- IQSTREAM_SetDiskFilenameBaseW()
    - IQSTREAM_SetDiskFilenameBase() is used instead.

Some helper methods have been included as well, which help to make some
common tasks a bit easier to perform. These are included at the very
bottom of the file.

If you need to extend this wrapper to support additional API functions,
it should be relatively straightforward to do so.

Depending on your use case (and ability to compile it without errors),
it may be worth checking out the Tektronix Python/Cython RSA API.

* Add notes on testing
* Convert this huge comment to a readme?
"""
import tempfile
import numpy as np
from ctypes import *
from enum import Enum
from os.path import dirname, realpath
from time import sleep

""" LOAD RSA DRIVER """

soDir = dirname(realpath(__file__))
RTLD_LAZY = 0x0001
LAZYLOAD = RTLD_LAZY | RTLD_GLOBAL
rsa = CDLL(soDir+'/drivers/libRSA_API.so', LAZYLOAD)
usbapi = CDLL(soDir+'/drivers/libcyusb_shared.so', LAZYLOAD)

""" GLOBAL CONSTANTS """

MAX_NUM_DEVICES = 10 # Max num. of devices that could be found
MAX_SERIAL_STRLEN = 8 # Bytes allocated for serial number string
MAX_DEVTYPE_STRLEN = 8 # Bytes allocated for device type string
FPGA_VERSION_STRLEN = 6 # Bytes allocated for FPGA version number string
FW_VERSION_STRLEN = 6 # Bytes allocated for FW version number string
HW_VERSION_STRLEN = 4 # Bytes allocated for HW version number string
NOMENCLATURE_STRLEN = 8 # Bytes allocated for device nomenclature string
API_VERSION_STRLEN = 8 # Bytes allocated for API version number string
DEVINFO_MAX_STRLEN = 100 # Bytes for date/time string
MAX_IQBLK_RECLEN = 126000000 # Maximum IQBLK Record Length

""" ENUMERATION TUPLES """

DEVEVENT = ('OVERRANGE', 'TRIGGER', '1PPS')
FREQREF_SOURCE = ('INTERNAL', 'EXTREF', 'GNSS', 'USER')
IQSOUTDEST = ('CLIENT', 'FILE_TIQ', 'FILE_SIQ', 'FILE_SIQ_SPLIT')
IQSOUTDTYPE = ('SINGLE', 'INT32', 'INT16', 'SINGLE_SCALE_INT32')
REFTIME_SRC = ('NONE', 'SYSTEM', 'GNSS', 'USER')
SPECTRUM_DETECTORS = ('PosPeak', 'NegPeak', 'AverageVRMS', 'Sample')
SPECTRUM_TRACES = ('Trace1', 'Trace2', 'Trace3')
SPECTRUM_VERTICAL_UNITS = ('dBm', 'Watt', 'Volt', 'Amp', 'dBmV')
SPECTRUM_WINDOWS = ('Kaiser', 'Mil6dB', 'BlackmanHarris', 'Rectangular',
                    'FlatTop', 'Hann')
TRIGGER_MODE = ('freeRun', 'triggered')
TRIGGER_SOURCE = ('External', 'IFPowerLevel')
TRIGGER_TRANSITION = ('LH', 'HL', 'Either')

""" CUSTOM DATA STRUCTURES """

class SPECTRUM_LIMITS(Structure):
    _fields_ = [('maxSpan', c_double),
                ('minSpan', c_double),
                ('maxRBW', c_double),
                ('minRBW', c_double),
                ('maxVBW', c_double),
                ('minVBW', c_double),
                ('maxTraceLength', c_int),
                ('minTraceLength', c_int)]

class SPECTRUM_SETTINGS(Structure):
    _fields_ = [('span', c_double),
                ('rbw', c_double),
                ('enableVBW', c_bool),
                ('vbw', c_double),
                ('traceLength', c_int),
                ('window', c_int),
                ('verticalUnit', c_int),
                ('actualStartFreq', c_double),
                ('actualStopFreq', c_double),
                ('actualFreqStepSize', c_double),
                ('actualRBW', c_double),
                ('actualVBW', c_double),
                ('actualNumIQSamples', c_int)]

class SPECTRUM_TRACEINFO(Structure):
    _fields_ = [('timestamp', c_int64),
                ('acqDataStatus', c_uint16)]

class IQBLK_ACQINFO(Structure):
    _fields_ = [('sample0Timestamp', c_uint64),
                ('triggerSampleIndex', c_uint64),
                ('triggerTimestamp', c_uint64),
                ('acqStatus', c_uint32)]

class IQSTREAM_File_Info(Structure):
    _fields_ = [('numberSamples', c_uint64),
                ('sample0Timestamp', c_uint64),
                ('triggerSampleIndex', c_uint64),
                ('triggerTimestamp', c_uint64),
                ('acqStatus', c_uint32),
                ('filenames', c_wchar_p)]

""" ERROR HANDLING """

class RSA_Error(Exception):
    def __init__(self, err_txt=""):
        self.err_txt = err_txt
        err = "RSA Error:\r\n{}".format(self.err_txt)
        super(RSA_Error, self).__init__(err)

class ReturnStatus(Enum):
    noError = 0

    # Connection
    errorNotConnected = 101
    errorIncompatibleFirmware = 102
    errorBootLoaderNotRunning = 103
    errorTooManyBootLoadersConnected = 104
    errorRebootFailure = 105

    # POST
    errorPOSTFailureFPGALoad = 201
    errorPOSTFailureHiPower = 202
    errorPOSTFailureI2C = 203
    errorPOSTFailureGPIF = 204
    errorPOSTFailureUsbSpeed = 205
    errorPOSTDiagFailure = 206

    # General Msmt
    errorBufferAllocFailed = 301
    errorParameter = 302
    errorDataNotReady = 304

    # Spectrum
    errorParameterTraceLength = 1101
    errorMeasurementNotEnabled = 1102
    errorSpanIsLessThanRBW = 1103
    errorFrequencyOutOfRange = 1104

    # IF streaming
    errorStreamADCToDiskFileOpen = 1201
    errorStreamADCToDiskAlreadyStreaming = 1202
    errorStreamADCToDiskBadPath = 1203
    errorStreamADCToDiskThreadFailure = 1204
    errorStreamedFileInvalidHeader = 1205
    errorStreamedFileOpenFailure = 1206
    errorStreamingOperationNotSupported = 1207
    errorStreamingFastForwardTimeInvalid = 1208
    errorStreamingInvalidParameters = 1209
    errorStreamingEOF = 1210

    # IQ streaming
    errorIQStreamInvalidFileDataType = 1301
    errorIQStreamFileOpenFailed = 1302
    errorIQStreamBandwidthOutOfRange = 1303

    # -----------------
    # Internal errors
    # -----------------
    errorTimeout = 3001
    errorTransfer = 3002
    errorFileOpen = 3003
    errorFailed = 3004
    errorCRC = 3005
    errorChangeToFlashMode = 3006
    errorChangeToRunMode = 3007
    errorDSPLError = 3008
    errorLOLockFailure = 3009
    errorExternalReferenceNotEnabled = 3010
    errorLogFailure = 3011
    errorRegisterIO = 3012
    errorFileRead = 3013

    errorDisconnectedDeviceRemoved = 3101
    errorDisconnectedDeviceNodeChangedAndRemoved = 3102
    errorDisconnectedTimeoutWaitingForADcData = 3103
    errorDisconnectedIOBeginTransfer = 3104
    errorOperationNotSupportedInSimMode = 3015

    errorFPGAConfigureFailure = 3201
    errorCalCWNormFailure = 3202
    errorSystemAppDataDirectory = 3203
    errorFileCreateMRU = 3204
    errorDeleteUnsuitableCachePath = 3205
    errorUnableToSetFilePermissions = 3206
    errorCreateCachePath = 3207
    errorCreateCachePathBoost = 3208
    errorCreateCachePathStd = 3209
    errorCreateCachePathGen = 3210
    errorBufferLengthTooSmall = 3211
    errorRemoveCachePath = 3212
    errorGetCachingDirectoryBoost = 3213
    errorGetCachingDirectoryStd = 3214
    errorGetCachingDirectoryGen = 3215
    errorInconsistentFileSystem = 3216

    errorWriteCalConfigHeader = 3301
    errorWriteCalConfigData = 3302
    errorReadCalConfigHeader = 3303
    errorReadCalConfigData = 3304
    errorEraseCalConfig = 3305
    errorCalConfigFileSize = 3306
    errorInvalidCalibConstantFileFormat = 3307
    errorMismatchCalibConstantsSize = 3308
    errorCalConfigInvalid = 3309

    # flash
    errorFlashFileSystemUnexpectedSize = 3401,
    errorFlashFileSystemNotMounted = 3402
    errorFlashFileSystemOutOfRange = 3403
    errorFlashFileSystemIndexNotFound = 3404
    errorFlashFileSystemReadErrorCRC = 3405
    errorFlashFileSystemReadFileMissing = 3406
    errorFlashFileSystemCreateCacheIndex = 3407
    errorFlashFileSystemCreateCachedDataFile = 3408
    errorFlashFileSystemUnsupportedFileSize = 3409
    errorFlashFileSystemInsufficentSpace = 3410
    errorFlashFileSystemInconsistentState = 3411
    errorFlashFileSystemTooManyFiles = 3412
    errorFlashFileSystemImportFileNotFound = 3413
    errorFlashFileSystemImportFileReadError = 3414
    errorFlashFileSystemImportFileError = 3415
    errorFlashFileSystemFileNotFoundError = 3416
    errorFlashFileSystemReadBufferTooSmall = 3417
    errorFlashWriteFailure = 3418
    errorFlashReadFailure = 3419
    errorFlashFileSystemBadArgument = 3420
    errorFlashFileSystemCreateFile = 3421

    # Aux monitoring
    errorMonitoringNotSupported = 3501,
    errorAuxDataNotAvailable = 3502

    # battery
    errorBatteryCommFailure = 3601
    errorBatteryChargerCommFailure = 3602
    errorBatteryNotPresent = 3603

    # EST
    errorESTOutputPathFile = 3701
    errorESTPathNotDirectory = 3702
    errorESTPathDoesntExist = 3703
    errorESTUnableToOpenLog = 3704
    errorESTUnableToOpenLimits = 3705

    # Revision information
    errorRevisionDataNotFound = 3801

    # alignment
    error112MHzAlignmentSignalLevelTooLow = 3901
    error10MHzAlignmentSignalLevelTooLow = 3902
    errorInvalidCalConstant = 3903
    errorNormalizationCacheInvalid = 3904
    errorInvalidAlignmentCache = 3905

    # acq status
    errorADCOverrange = 9000  # must not change the location of these error codes without coordinating with MFG TEST
    errorOscUnlock = 9001

    errorNotSupported = 9901

    errorPlaceholder = 9999
    notImplemented = -1

def err_check(rs):
    """Obtain internal API ErrorStatus and pass to RSA_Error."""
    if ReturnStatus(rs) != ReturnStatus.noError:
        raise RSA_Error(ReturnStatus(rs).name)

def check_range(input, min, max, incl=True):
    """Check if input is in valid range, inclusive or exclusive"""
    if incl:
        if min <= input <= max:
            return input
        else:
            raise ValueError("Input must be in range {} to {}".format(min, max)
                + ", inclusive.")
    else:
        if min < input < max:
            return input
        else:
            raise ValueError("Input must be in range {} to {}".format(min, max)
                + ", exclusive.")

def check_int(input):
    """Check if input is an integer."""
    if type(input) is int:
        return input
    elif type(input) is float and input.is_integer():
        # Accept floats if they are whole numbers
        return int(input)
    else:
        raise TypeError("Input must be an integer.")

def check_string(input):
    """Check if input is a string."""
    if type(input) is str:
        return input
    else:
        raise TypeError("Input must be a string.")

def check_num(input):
    """Check if input is a number (float or int)."""
    if type(input) is int or type(input) is float:
        return input
    else:
        raise TypeError("Input must be a number (float or int).")

def check_bool(input):
    """Check if input is a boolean."""
    if type(input) is bool:
        return input
    else:
        raise TypeError("Input must be a boolean.")

""" ALIGNMENT METHODS """

def ALIGN_GetAlignmentNeeded():
    """
    Determine if an alignment is needed or not.

    This is based on the difference between the current temperature
    and the temperature from the last alignment.

    Returns
    -------
    bool
        True indicates an alignment is needed, False for not needed.
    """
    needed = c_bool()
    err_check(rsa.ALIGN_GetAlignmentNeeded(byref(needed)))
    return needed.value

def ALIGN_GetWarmupStatus():
    """
    Report device warm-up status.

    Devices start in the "warm-up" state after initial power up until
    the internal temperature stabilizes. The warm-up interval is
    different for different devices.

    Returns
    -------
    bool
        True indicates device warm-up interval reached.
        False indicates warm-up has not been reached
    """
    warmedUp = c_bool()
    err_check(rsa.ALIGN_GetWarmupStatus(byref(warmedUp)))
    return warmedUp.value

def ALIGN_RunAlignment():
    """Run the device alignment process."""
    err_check(rsa.ALIGN_RunAlignment())

""" AUDIO METHODS """

def AUDIO_SetFrequencyOffset(freqOffsetHz):
    """
    Set the audio carrier frequency offset from the center frequency.

    This method allows the audio demodulation carrier frequency to be
    offset from the device's center frequency. This allows tuning
    different carrier frequencies without changing the center
    frequency. The audio demodulation is performed at a carrier
    frequency of (center frequency + freqOffsetHz). The freqOffsetHz is
    set to an initial value of 0 Hz at the time the device is connected.

    Parameters
    ----------
    freqOffsetHz : float
        Amount of frequency offset from the center frequency, in Hz.
        Range: -20e6 <= freqOffsetHz <= 20e6
    """
    freqOffsetHz = check_num(freqOffsetHz)
    freOffsetHz = check_range(freqOffsetHz, -20e6, 20e6)
    err_check(rsa.AUDIO_SetFrequencyOffset(c_double(freqOffsetHz)))

def AUDIO_GetFrequencyOffset():
    """
    Query the audio carrier frequency offset from the center frequency.

    Returns
    -------
    float
        Current audio frequency offset from the center frequency in Hz.
    """
    freqOffsetHz = c_double()
    err_check(rsa.AUDIO_GetFrequencyOffset(byref(freqOffsetHz)))
    return freqOffsetHz.value

def AUDIO_GetEnable():
    """
    Query the audio demodulation run state.

    Returns
    -------
    bool
        True indicates audio demodulation is running.
        False indicates it is stopped.
    """
    enable = c_bool()
    err_check(rsa.AUDIO_GetEnable(byref(enable)))
    return enable.value

def AUDIO_GetData(inSize):
    """
    Return audio sample data in a user buffer.

    Parameters
    ----------
    inSize : int
        Maximum amount of audio data samples allowed.

    Returns
    -------
    data : Numpy array
        Contains an array of audio data as integers.
    """
    inSize = check_int(inSize)
    inSize = check_range(inSize, 0, float('inf'))
    data = (c_int16 * inSize)()
    outSize = c_uint16()
    err_check(rsa.AUDIO_GetData(byref(data), c_uint16(inSize), byref(outSize)))
    return np.ctypeslib.as_array(data)

def AUDIO_GetMode():
    """
    Query the audio demodulation mode.

    The audio demodulation mode must be set manually before querying.

    Returns
    -------
    int
        The audio demodulation mode. Valid results 0, 1, 2, 3, 4, or 5.
            Corresponding, respectively, to:
            FM_8KHZ, FM_13KHZ, FM_75KHZ, FM_200KHZ, AM_8KHZ, or NONE.

    Raises
    ------
    RSA_Error
        If the audio demodulation mode has not yet been set.
    """
    mode = c_int()
    err_check(rsa.AUDIO_GetMode(byref(mode)))
    if mode.value > 5 or mode.value < 0:
        raise RSA_Error("Audio demodulation mode has not yet been set.")
    return mode.value

def AUDIO_GetMute():
    """
    Query the status of the mute operation.

    The status of the mute operation does not stop the audio processing
    or data callbacks.

    Returns
    -------
    bool
        The mute status of the output speakers. True indicates output
            is muted, False indicates output is not muted.
    """
    mute = c_bool()
    err_check(rsa.AUDIO_GetMute(byref(mute)))
    return mute.value

def AUDIO_GetVolume():
    """Query the volume, which must be a real value from 0 to 1."""
    volume = c_float()
    err_check(rsa.AUDIO_GetVolume(byref(volume)))
    return volume.value

def AUDIO_SetMode(mode):
    """
    Set the audio demodulation mode.

    Parameters
    ----------
    mode : int
        Desired audio demodulation mode. Valid settings:
            0, 1, 2, 3, 4, 5. Corresponding respectively to:
            FM_8KHZ, FM_13KHZ, FM_75KHZ, FM_200KHZ, AM_8KHZ, NONE
    """
    mode = check_int(mode)
    mode = check_range(mode, 0, 5)
    err_check(rsa.AUDIO_SetMode(c_int(mode)))

def AUDIO_SetMute(mute):
    """
    Set the mute status.

    Does not affect the data processing or callbacks.

    Parameters
    ----------
    mute : bool
        Mute status. True mutes the output, False restores the output.
    """
    mute = check_bool(mute)
    err_check(rsa.AUDIO_SetMute(c_bool(mute)))

def AUDIO_SetVolume(volume):
    """
    Set the volume value.

    Input must be a real number ranging from 0 to 1. If the value is
    outside of the specified range, clipping occurs.

    Parameters
    ----------
    volume : float
        Volume value. Range: 0.0 to 1.0.
    """
    volume = check_num(volume)
    volume = check_range(volume, 0.0, 1.0)
    err_check(rsa.AUDIO_SetVolume(c_float(volume)))

def AUDIO_Start():
    """Start the audio demodulation output generation."""
    err_check(rsa.AUDIO_Start())

def AUDIO_Stop():
    """Stop the audio demodulation output generation."""
    err_check(rsa.AUDIO_Stop())

""" CONFIG METHODS """

def CONFIG_GetCenterFreq():
    """Return the current center frequency in Hz."""
    cf = c_double()
    err_check(rsa.CONFIG_GetCenterFreq(byref(cf)))
    return cf.value

def CONFIG_GetExternalRefEnable():
    """
    Return the state of the external reference.

    This method is less useful than CONFIG_GetFrequencyReferenceSource(),
    because it only indicates if the external reference is chosen or
    not. The CONFIG_GetFrequencyReferenceSource() method indicates all
    available sources, and should often be used in place of this one.

    Returns
    -------
    bool
        True means external reference is enabled, False means disabled.
    """
    exRefEn = c_bool()
    err_check(rsa.CONFIG_GetExternalRefEnable(byref(exRefEn)))
    return exRefEn.value

def CONFIG_GetExternalRefFrequency():
    """
    Return the frequency, in Hz, of the external reference.

    The external reference input must be enabled for this method to
    return useful results.

    Returns
    -------
    float
        The external reference frequency, measured in Hz.

    Raises
    ------
    RSA_Error
        If there is no external reference input in use.
    """
    src = CONFIG_GetFrequencyReferenceSource()
    if src == FREQREF_SOURCE[0]:
        raise RSA_Error("External frequency reference not in use.")
    else:
        extFreq = c_double()
        err_check(rsa.CONFIG_GetExternalRefFrequency(byref(extFreq)))
        return extFreq.value

def CONFIG_GetFrequencyReferenceSource():
    """
    Return a string representing the frequency reference source.

    Note: The RSA306 and RSA306B support only INTERNAL and EXTREF
    sources.

    Returns
    -------
    string
        Name of the frequency reference source. Valid results:
            INTERNAL : Internal frequency reference.
            EXTREF : External (Ref In) frequency reference.
            GNSS : Internal GNSS receiver reference
            USER : Previously set USER setting, or, if none, INTERNAL.
    """
    src = c_int()
    err_check(rsa.CONFIG_GetFrequencyReferenceSource(byref(src)))
    return FREQREF_SOURCE[src.value]

def CONFIG_GetMaxCenterFreq():
    """Return the maximum center frequency in Hz."""
    maxCF = c_double()
    err_check(rsa.CONFIG_GetMaxCenterFreq(byref(maxCF)))
    return maxCF.value

def CONFIG_GetMinCenterFreq():
    """Return the minimum center frequency in Hz."""
    minCF = c_double()
    err_check(rsa.CONFIG_GetMinCenterFreq(byref(minCF)))
    return minCF.value

def CONFIG_GetReferenceLevel():
    """Return the current reference level, measured in dBm."""
    refLevel = c_double()
    err_check(rsa.CONFIG_GetReferenceLevel(byref(refLevel)))
    return refLevel.value

def CONFIG_Preset():
    """
    Set the connected device to preset values.

    This method sets the trigger mode to Free Run, the center frequency
    to 1.5 GHz, the span to 40 MHz, the IQ record length to 1024 
    samples, and the reference level to 0 dBm.
    """
    err_check(rsa.CONFIG_Preset())
    err_check(rsa.IQBLK_SetIQRecordLength(1024))

def CONFIG_SetCenterFreq(cf):
    """
    Set the center frequency value, in Hz.

    When using the tracking generator, be sure to set the tracking
    generator output level before setting the center frequency.

    Parameters
    ----------
    cf : float or int
        Value to set center frequency, in Hz.
    """
    cf = check_num(cf)
    cf = check_range(cf, CONFIG_GetMinCenterFreq(), CONFIG_GetMaxCenterFreq())
    err_check(rsa.CONFIG_SetCenterFreq(c_double(cf)))

def CONFIG_SetExternalRefEnable(exRefEn):
    """
    Enable or disable the external reference.

    When the external reference is enabled, an external reference
    signal must be connected to the "Ref In" port. The signal must have
    a frequency of 10 MHz with a +10 dBm maximum amplitude. This signal
    is used by the local oscillators to mix with the input signal.

    When the external reference is disabled, an internal reference
    source is used.

    Parameters
    ----------
    exRefEn : bool
        True enables the external reference. False disables it.
    """
    exRefEn = check_bool(exRefEn)
    err_check(rsa.CONFIG_SetExternalRefEnable(c_bool(exRefEn)))

def CONFIG_SetFrequencyReferenceSource(src):
    """
    Select the device frequency reference source.

    Note: RSA306B and RSA306 support only INTERNAL and EXTREF sources.

    The INTERNAL source is always a valid selection, and is never
    switched out of automatically.

    The EXTREF source uses the signal input to the Ref In connector as
    frequency reference for the internal oscillators. If EXTREF is
    selected without a valid signal connected to Ref In, the source
    automatically switches to USER if available, or to INTERNAL
    otherwise. If lock fails, an error status indicating the failure is
    returned.

    The GNSS source uses the internal GNSS receiver to adjust the
    internal reference oscillator. If GNSS source is selected, the GNSS
    receiver must be enabled. If the GNSS receiver is not enabled, the
    source selection remains GNSS, but no frequency correction is done.
    GNSS disciplining only occurs when the GNSS receiver has navigation
    lock. When the receiver is unlocked, the adjustment setting is
    retained unchanged until receiver lock is achieved or the source is
    switched to another selection

    If USER source is selected, the previously set USER setting is
    used. If the USER setting has not been set, the source switches
    automatically to INTERNAL.

    Parameters
    ----------
    src : string
        Frequency reference source selection. Valid settings:
            INTERNAL : Internal frequency reference.
            EXTREF : External (Ref In) frequency reference.
            GNSS : Internal GNSS receiver reference
            USER : Previously set USER setting, or, if none, INTERNAL.

    Raises
    ------
    RSA_Error
        If the input string does not match one of the valid settings.
    """
    src = check_string(src)
    if src in FREQREF_SOURCE:
        if src is 'GNSS':
            raise RSA_Error("RSA 306B does not support GNSS reference.")
        else:
            value = c_int(FREQREF_SOURCE.index(src))
            err_check(rsa.CONFIG_SetFrequencyReferenceSource(value))
    else:
        raise RSA_Error("Input does not match a valid setting.")

def CONFIG_SetReferenceLevel(refLevel):
    """
    Set the reference level

    The reference level controls the signal path gain and attenuation
    settings. The value should be set to the maximum expected signal
    power level in dBm. Setting the value too low may result in over-
    driving the signal path and ADC, while setting it too high results
    in excess noise in the signal.

    Parameters
    ----------
    refLevel : float or int
        Reference level, in dBm. Valid range: -130 dBm to 30 dBm.
    """
    refLevel = check_num(refLevel)
    refLevel = check_range(refLevel, -130, 30)
    err_check(rsa.CONFIG_SetReferenceLevel(c_double(refLevel)))

""" DEVICE METHODS """

def DEVICE_Connect(deviceID=0):
    """
    Connect to a device specified by the deviceID parameter.

    If a single device is attached, no parameter needs to be given. If
    multiple devices are attached, a deviceID value must be given to
    identify which device is the target for connection.

    The deviceID value can be found using the search() method.

    Parameters
    ----------
    deviceID : int
        The deviceID of the target device.
    """
    deviceID = check_int(deviceID)
    deviceID = check_range(deviceID, 0, float('inf'))
    err_check(rsa.DEVICE_Connect(c_int(deviceID)))

def DEVICE_Disconnect():
    """Stop data acquisition and disconnect from connected device."""
    err_check(rsa.DEVICE_Disconnect())

def DEVICE_GetEnable():
    """
    Query the run state.

    The device only produces data results when in the run state, when
    signal samples flow from the device to the host API.

    Returns
    -------
    bool
       True indicates the device is in the run state. False indicates
       that it is in the stop state.
    """
    enable = c_bool()
    err_check(rsa.DEVICE_GetEnable(byref(enable)))
    return enable.value

def DEVICE_GetFPGAVersion():
    """
    Retrieve the FPGA version number.

    The FPGA version has the form "Vmajor.minor" - for example, "V3.4"
    indicates a major version of 3, and a minor version of 4. The
    maximum total string length supported is 6 characters.

    Returns
    -------
    string
        The FPGA version number, formatted as described above.
    """
    fpgaVersion = (c_char * FPGA_VERSION_STRLEN)()
    err_check(rsa.DEVICE_GetFPGAVersion(byref(fpgaVersion)))
    return fpgaVersion.value.decode('utf-8')

def DEVICE_GetFWVersion():
    """
    Retrieve the firmware version number.

    The firmware version number has the form: "Vmajor.minor". For
    example: "V3.4", for major version 3, minor version 4. The
    maximum total string length supported is 6 characters.

    Returns
    -------
    string
        The firmware version number, formatted as described above.
    """
    fwVersion = (c_char * FW_VERSION_STRLEN)()
    err_check(rsa.DEVICE_GetFWVersion(byref(fwVersion)))
    return fwVersion.value.decode('utf-8')

def DEVICE_GetHWVersion():
    """
    Retrieve the hardware version number.

    The firmware version number has the form: "VversionNumber". For
    example: "V3". The maximum string length supported is 4 characters.

    Returns
    -------
    string
        The hardware version number, formatted as described above.
    """
    hwVersion = (c_char * HW_VERSION_STRLEN)()
    err_check(rsa.DEVICE_GetHWVersion(byref(hwVersion)))
    return hwVersion.value.decode('utf-8')

def DEVICE_GetNomenclature():
    """
    Retrieve the name of the device.

    The nomenclature has the form "RSA306B", for example. The maximum
    string length supported is 8 characters.

    Returns
    -------
    string
        Name of the device.
    """
    nomenclature = (c_char * NOMENCLATURE_STRLEN)()
    err_check(rsa.DEVICE_GetNomenclature(byref(nomenclature)))
    return nomenclature.value.decode('utf-8')

def DEVICE_GetSerialNumber():
    """
    Retrieve the serial number of the device.

    The serial number has the form "B012345", for example. The maximum
    string length supported is 8 characters.

    Returns
    -------
    string
        Serial number of the device.
    """
    serialNum = (c_char * MAX_SERIAL_STRLEN)()
    err_check(rsa.DEVICE_GetSerialNumber(byref(serialNum)))
    return serialNum.value.decode('utf-8')

def DEVICE_GetAPIVersion():
    """
    Retrieve the API version number.

    The API version number has the form: "major.minor.revision", for
    example: "3.4.0145", for major version 3, minor version 4, and
    revision 0145. The maximum string length supported is 8 characters.

    Returns
    -------
    string
        The API version number, formatted as described above.
    """
    apiVersion = (c_char * API_VERSION_STRLEN)()
    err_check(rsa.DEVICE_GetAPIVersion(byref(apiVersion)))
    return apiVersion.value.decode('utf-8')

def DEVICE_PrepareForRun():
    """
    Put the system in a known state, ready to stream data.

    This method does not actually initiate data transfer. During file
    playback mode, this is useful to allow other parts of your
    application to prepare to receive data before starting the
    transfer. See DEVICE_StartFrameTransfer(). This is in comparison to
    the DEVICE_Run() method, which immediately starts data streaming
    without waiting for a "go" signal.
    """
    err_check(rsa.DEVICE_PrepareForRun())

def DEVICE_GetInfo():
    """
    Retrieve multiple device and information strings.

    Obtained information includes: device nomenclature, serial number,
    firmware versionn, FPGA version, hardware version, and API version.

    Returns
    -------
    dict
        All of the above listed information as strings.
        Keys: nomenclature, serialNum, fwVersion, fpgaVersion,
              hwVersion, apiVersion
    """
    nomenclature = DEVICE_GetNomenclature()
    serialNum = DEVICE_GetSerialNumber()
    fwVersion = DEVICE_GetFWVersion()
    fpgaVersion = DEVICE_GetFPGAVersion()
    hwVersion = DEVICE_GetHWVersion()
    apiVersion = DEVICE_GetAPIVersion()
    info = {
        "nomenclature" : nomenclature,
        "serialNum" : serialNum,
        "fwVersion" : fwVersion,
        "fpgaVersion" : fpgaVersion,
        "hwVersion" : hwVersion,
        "apiVersion" : apiVersion
    }
    return info

def DEVICE_GetOverTemperatureStatus():
    """
    Query device for over-temperature status.

    This method allows clients to monitor the device's internal
    temperature status when operating in high-temperature environments.
    If the over-temperature condition is detected, the device should be
    powered down or moved to a lower temperature area.

    Returns
    -------
    bool
        Over-temperature status. True indicates device above nominal
        safe operating range, and may result in reduced accuracy and/
        or damage to the device. False indicates device temperature is
        within the safe operating range.
    """
    overTemp = c_bool()
    err_check(rsa.DEVICE_GetOverTemperatureStatus(byref(overTemp)))
    return overTemp.value

def DEVICE_Reset(deviceID=-1):
    """
    Reboot the specified device.

    If a single device is attached, no parameter needs to be given. If
    multiple devices are attached, a deviceID value must be given to
    identify which device to reboot.

    Parameters
    ----------
    deviceID : int
        The deviceID of the target device.

    Raises
    ------
    RSA_Error
        If multiple devices are found but no deviceID is specified.
    """
    DEVICE_Disconnect()
    foundDevices = DEVICE_Search()
    numFound = len(foundDevices)
    if numFound == 1:
        deviceID = 0
    elif numFound > 1 and deviceID == -1:
        raise RSA_Error("Multiple devices found, but no ID specified.")
    deviceID = check_int(deviceID)
    err_check(rsa.DEVICE_Reset(c_int(deviceID)))   

def DEVICE_Run():
    """Start data acquisition."""
    err_check(rsa.DEVICE_Run()) 

def DEVICE_Search():
    """
    Search for connectable devices.

    Returns a dict with an entry containing the device ID number,
    serial number, and device type information for each device found.
    An example of this would be: {0 : ('B012345', 'RSA306B')}, when a 
    single RSA306B is found, with serial number 'B012345'.

    Valid deviceType strings are "RSA306", "RSA306B", "RSA503A",
    "RSA507A", "RSA603A", and "RSA607A".

    Returns
    -------
    dict
        Found devices: {deviceID : (deviceSerial, deviceType)}.
            deviceID : int
            deviceSerial : string
            deviceType : string

    Raises
    ------
    RSA_Error
        If no devices are found.
    """
    numFound = c_int()
    devIDs = (c_int * MAX_NUM_DEVICES)()
    devSerial = ((c_char * MAX_NUM_DEVICES) * MAX_SERIAL_STRLEN)()
    devType = ((c_char * MAX_NUM_DEVICES) * MAX_DEVTYPE_STRLEN)()

    err_check(rsa.DEVICE_Search(byref(numFound), byref(devIDs),devSerial,
        devType))

    foundDevices = {
        ID : (devSerial[ID].value.decode(), devType[ID].value.decode()) \
        for ID in devIDs
    }

    # If there are no devices, there is still a dict returned
    # with a device ID, but the other elements are empty.
    if foundDevices[0] == ('',''):
        raise RSA_Error("Could not find a matching Tektronix RSA device.")
    else:
        return foundDevices

def DEVICE_StartFrameTransfer():
    """
    Start data transfer.

    This is typically used as the trigger to start data streaming after
    a call to DEVICE_PrepareForRun(). If the system is in the stopped
    state, this call places it back into the run state with no changes
    to any internal data or settings, and data streaming will begin
    assuming there are no errors.
    """
    err_check(rsa.DEVICE_StartFrameTransfer())

def DEVICE_Stop():
    """
    Stop data acquisition.

    This method must be called when changes are made to values that
    affect the signal.
    """
    err_check(rsa.DEVICE_Stop())

def DEVICE_GetEventStatus(eventID):
    """
    Return global device real-time event status.

    The device should be in the Run state when this method is called.
    Event information is only updated in the Run state, not in the Stop
    state.

    Overrange event detection requires no additional configuration to
    activate. The event indicates that the ADC input signal exceeded
    the allowable range, and signal clipping has likely occurred. The
    reported timestamp value is the most recent USB transfer frame in
    which a signal overrange was detected.

    Trigger event detection requires the appropriate HW trigger
    settings to be configured. These include trigger mode, source,
    transition, and IF power level (if IF power trigger is selected).
    The event indicates that the trigger condition has occurred. The
    reported timestamp value is of the most recent sample instant when
    a trigger event was detected. The forceTrigger() method can be used
    to simulate a trigger event.

    1PPS event detection (RSA500AA/600A only) requires the GNSS receiver
    to be enabled and have navigation lock. The even indicates that the
    1PPS event has occurred. The reported timestamp value is of the
    most recent sample instant when the GNSS Rx 1PPS pulse rising edge
    was detected.

    Querying an event causes the information for that event to be
    cleared after its state is returned. Subsequent queries will
    report "no event" until a new one occurs. All events are cleared
    when the device state transitions from Stop to Run.

    Parameters
    ----------
    eventID : string
        Identifier for the event status to query. Valid settings:
            OVERRANGE : Overrange event detection.
            TRIGGER : Trigger event detection.
            1PPS : 1PPS event detection (RSA500AA/600A only).

    Returns
    -------
    occurred : bool
        Indicates whether the event has occurred.
    timestamp : int
        Event occurrence timestamp. Only valid if occurred is True.

    Raises
    ------
    RSA_Error
        If the input string does not match one of the valid settings.
    """
    occurred  = c_bool()
    timestamp = c_uint64()
    eventID = check_string(eventID)
    if eventID in DEVEVENT:
        value = c_int(DEVEVENT.index(eventID))
    else:
        raise RSA_Error("Input string does not match one of the valid settings.")
    err_check(rsa.DEVICE_GetEventStatus(value, byref(occurred),
        byref(timestamp)))
    return occurred.value, timestamp.value

""" GNSS METHODS """

def GNSS_GetHwInstalled():
    """
    Return whether internal GNSS receiver hardware is installed.

    GNSS hardware is only installed in RSA500AA and RSA600A devices.
    All other devices will indicate no hardware installed.

    Returns
    -------
    bool
        True indicates GNSS receiver HW installed, False otherwise.
    """
    installed = c_bool()
    err_check(rsa.GNSS_GetHwInstalled(byref(installed)))
    return installed.value

""" IQ BLOCK METHODS """

def IQBLK_GetIQAcqInfo():
    """
    Return IQ acquisition status info for the most recent IQ block.

    IQBLK_GetIQAcqInfo() may be called after an IQ block record is
    retrieved with IQBLK_GetIQData(), IQBLK_GetIQDataInterleaved(), or
    IQBLK_GetIQDataComplex(). The returned information applies to the
    IQ record returned by the "GetData" methods.

    The acquisition status bits returned by this method are:
        Bit 0 : INPUT_OVERRANGE
            ADC input overrange during acquisition.
        Bit 1 : FREQREF_UNLOCKED
            Frequency reference unlocked during acquisition.
        Bit 2 : ACQ_SYS_ERROR
            Internal oscillator unlocked or power failure during
            acquisition.
        Bit 3 : DATA_XFER_ERROR
            USB frame transfer error detected during acquisition.

    A status bit value of 1 indicates that event occurred during the
    signal acquisition. A value of 0 indicates no occurrence.

    Returns
    -------
    sample0Timestamp : int
        Timestamp of the first sample of the IQ block record.
    triggerSampleIndex : int
        Index to the sample corresponding to the trigger point.
    triggerTimestamp : int
        Timestamp of the trigger sample.
    acqStatus : int
        "Word" with acquisition status bits. See above for details.
    """
    acqInfo = IQBLK_ACQINFO()
    err_check(rsa.IQBLK_GetIQAcqInfo(byref(acqInfo)))
    info = (acqInfo.sample0Timestamp.value, acqInfo.triggerSampleIndex.value,
        acqInfo.triggerTimestamp.value, acqInfo.acqStatus.value)
    return info

def IQBLK_AcquireIQData():
    """
    Initiate an IQ block record acquisition.

    Calling this method initiates an IQ block record data acquisition.
    This method places the device in the Run state if it is not
    already in that state.

    Before calling this method, all device acquisition parameters must
    be set to valid states. These include Center Frequency, Reference
    Level, any desired Trigger conditions, and the IQBLK Bandwidth and
    Record Length settings.
    """
    err_check(rsa.IQBLK_AcquireIQData())

def IQBLK_GetIQBandwidth():
    """
    Query the IQ bandwidth value.

    Returns
    -------
    float
        The IQ bandwidth value.
    """
    iqBandwidth = c_double()
    err_check(rsa.IQBLK_GetIQBandwidth(byref(iqBandwidth)))
    return iqBandwidth.value

def IQBLK_GetIQData(reqLength):
    """
    Retrieve an IQ block data record in a single interleaved array.

    Parameters
    ----------
    reqLength : int
        Number of IQ sample pairs requested to be returned.
        The maximum value of reqLength is equal to the recordLength
        value set in IQBLK_SetIQRecordLength(). Smaller values allow
        retrieving partial IQ records.

    Returns
    -------
    Numpy array
        I-data and Q-data stored in a single array.
        I-data is stored at even indexes of the returned array,
        and Q-data is stored at the odd indexes.
    """
    reqLength = check_int(reqLength)
    reqLength = check_range(reqLength, 2, IQBLK_GetMaxIQRecordLength())
    outLength = c_int()
    iqData = (c_float * (reqLength*2))()
    err_check(rsa.IQBLK_GetIQData(byref(iqData), byref(outLength), c_int(reqLength)))
    return np.ctypeslib.as_array(iqData)

def IQBLK_GetIQDataDeinterleaved(reqLength):
    """
    Retrieve an IQ block data record in separate I and Q array format.

    When complete, the iData array is filled with I-data and the qData
    array is filled with Q-data. The Q-data is not imaginary.

    For example, with reqLength = N:
        iData: [I_0, I_1, ..., I_N]
        qData: [Q_0, Q_1, ..., Q_N]
        Actual IQ Data: [I_0 + i*Q_0, I_1 + i*Q_1, ..., I_N + i*Q_N]

    Parameters
    ----------
    reqLength : int
        Number of IQ samples requested to be returned in data arrays.
        The maximum value of reqLength is equal to the recordLength
        value set in IQBLK_SetIQRecordLength(). Smaller values of
        reqLength allow retrieving partial IQ records.

    Returns
    -------
    iData : Numpy array
        Array of I-data.
    qData : Numpy array
        Array of Q-data.
    """
    reqLength = check_int(reqLength)
    reqLength = check_range(reqLength, 2, IQBLK_GetMaxIQRecordLength())
    iData = (c_float * reqLength)()
    qData = (c_float * reqLength)()
    outLength = c_int()
    err_check(rsa.IQBLK_GetIQDataDeinterleaved(byref(iData), byref(qData), 
        byref(outLength), c_int(reqLength)))
    return np.ctypeslib.as_array(iData), np.ctypeslib.as_array(qData)

def IQBLK_GetIQRecordLength():
    """
    Query the IQ record length.

    The IQ record length is the number of IQ data samples to be
    generated with each acquisition.

    Returns
    -------
    int
        Number of IQ data samples to be generated with each acquisition.
    """
    recordLength = c_int()
    err_check(rsa.IQBLK_GetIQRecordLength(byref(recordLength)))
    return recordLength.value

def IQBLK_GetIQSampleRate():
    """
    Query the IQ sample rate value.

    The IQ sample rate value depends on the IQ bandwidth value. Set the
    IQ bandwidth value before querying the sample rate.

    Returns
    -------
    float
        The IQ sampling frequency, in samples/second.
    """
    iqSampleRate = c_double()
    err_check(rsa.IQBLK_GetIQSampleRate(byref(iqSampleRate)))
    return iqSampleRate.value

def IQBLK_GetMaxIQBandwidth():
    """
    Query the maximum IQ bandwidth of the connected device.

    Returns
    -------
    float
        The maximum IQ bandwidth, measured in Hz.
    """
    maxBandwidth = c_double()
    err_check(rsa.IQBLK_GetMaxIQBandwidth(byref(maxBandwidth)))
    return maxBandwidth.value

def IQBLK_GetMaxIQRecordLength():
    """
    Query the maximum IQ record length.

    The maximum IQ record length is the maximum number of samples which
    can be generated in one IQ block record. The maximum IQ record
    length varies as a function of the IQ bandwidth - set the bandwidth
    before querying the maximum record length. You should not request
    more than the maximum number of IQ samples when setting the record
    length. The maximum record length is the maximum number of IQ sample
    pairs that can be generated at the requested IQ bandwidth and
    corresponding IQ sample rate from 2 seconds of acquired signal data.

    Returns
    -------
    int
        The maximum IQ record length, measured in samples.
    """
    maxIqRecLen = c_int()
    err_check(rsa.IQBLK_GetMaxIQRecordLength(byref(maxIqRecLen)))
    return maxIqRecLen.value

def IQBLK_GetMinIQBandwidth():
    """
    Query the minimum IQ bandwidth of the connected device.

    Returns
    -------
    float
        The minimum IQ bandwidth, measured in Hz.
    """
    minBandwidth = c_double()
    err_check(rsa.IQBLK_GetMinIQBandwidth(byref(minBandwidth)))
    return minBandwidth.value

def IQBLK_SetIQBandwidth(iqBandwidth):
    """
    Set the IQ bandwidth value.

    The IQ bandwidth must be set before acquiring data. The input value
    must be within a valid range, and the IQ sample rate is determined
    by the IQ bandwidth.

    Parameters
    ----------
    iqBandwidth : float or int
        IQ bandwidth value measured in Hz
    """
    iqBandwidth = check_num(iqBandwidth)
    iqBandwidth = check_range(iqBandwidth, IQBLK_GetMinIQBandwidth(),
        IQBLK_GetMaxIQBandwidth())
    err_check(rsa.IQBLK_SetIQBandwidth(c_double(iqBandwidth)))

def IQBLK_SetIQRecordLength(recordLength):
    """
    Set the number of IQ samples generated by each IQ block acquisition.

    A check is performed to ensure that the desired value is within the
    allowed range. For best results in FFT analysis, choose a multiple
    of 2. The maximum allowed value is determined by the IQ bandwidth;
    set that first.

    Parameters
    ----------
    recordLength : int
        IQ record length, measured in samples. Minimum value of 2.
    """
    recordLength = check_int(recordLength)
    recordLength = check_range(recordLength, 2, IQBLK_GetMaxIQRecordLength())
    err_check(rsa.IQBLK_SetIQRecordLength(c_int(recordLength)))

def IQBLK_WaitForIQDataReady(timeoutMsec):
    """
    Wait for the data to be ready to be queried.

    Parameters
    ----------
    timeoutMsec : int
        Timeout value measured in ms.

    Returns
    -------
    bool
        True indicates data is ready for acquisition. False indicates
        the data is not ready and the timeout value is exceeded.
    """
    timeoutMsec = check_int(timeoutMsec)
    ready = c_bool()
    err_check(rsa.IQBLK_WaitForIQDataReady(c_int(timeoutMsec), byref(ready)))
    return ready.value

""" IQ STREAM METHODS """

def IQSTREAM_GetMaxAcqBandwidth():
    """
    Query the maximum IQ bandwidth for IQ streaming.

    The IQ streaming bandwidth should be set to a value no larger than
    the value returned by this method.

    Returns
    -------
    float
        The maximum IQ bandwidth supported by IQ streaming, in Hz.
    """
    maxBandwidthHz = c_double()
    err_check(rsa.IQSTREAM_GetMaxAcqBandwidth(byref(maxBandwidthHz)))
    return maxBandwidthHz.value

def IQSTREAM_GetMinAcqBandwidth():
    """
    Query the minimum IQ bandwidth for IQ streaming.

    The IQ streaming bandwidth should be set to a value no smaller than
    the value returned by this method.

    Returns
    -------
    float
        The minimum IQ bandwidth supported by IQ streaming, in Hz.
    """
    minBandwidthHz = c_double()
    err_check(rsa.IQSTREAM_GetMinAcqBandwidth(byref(minBandwidthHz)))
    return minBandwidthHz.value

def IQSTREAM_ClearAcqStatus():
    """
    Reset the "sticky" status bits of the acqStatus info element during
    an IQ streaming run interval.

    This is effective for both client and file destination runs.
    """
    err_check(rsa.IQSTREAM_ClearAcqStatus())

def IQSTREAM_GetAcqParameters():
    """
    Retrieve the processing parameters of IQ streaming output bandwidth
    and sample rate, resulting from the user's requested bandwidth.

    Call this method after calling IQSTREAM_SetAcqBandwidth() to set
    the requested bandwidth. See IQSTREAM_SetAcqBandwidth() docstring
    for details of how requested bandwidth is used to select output
    bandwidth and sample rate settings.

    Returns
    -------
    float: bwHz_act
        Actual acquisition bandwidth of IQ streaming output data in Hz.
    float: srSps
        Actual sample rate of IQ streaming output data in Samples/sec.
    """
    bwHz_act = c_double()
    srSps = c_double()
    err_check(rsa.IQSTREAM_GetAcqParameters(byref(bwHz_act), byref(srSps)))
    return bwHz_act.value, srSps.value

def IQSTREAM_GetDiskFileInfo():
    """
    Retrieve information about the previous file output operation.

    This information is intended to be queried after the file output
    operation has completed. It can be queried during file writing as
    an ongoing status, but some of the results may not be valid at that
    time.

    Note: This method does not return the filenames parameter as shown
    in the official API documentation.

    IQSTREAM_ClearAcqStatus() can be called to clear the "sticky" bits
    during the run if it is desired to reset them.

    Note: If acqStatus indicators show "Output buffer overflow", it is
    likely that the disk is too slow to keep up with writing the data
    generated by IQ stream processing. Use a faster disk (SSD is
    recommended), or a smaller acquisition bandwidth which generates
    data at a lower rate.

    Returns
    -------
    An IQSTREAM_File_Info structure which contains:
    numberSamples : int
        Number of IQ sample pairs written to the file.
    sample0Timestamp : int
        Timestamp of the first sample written to file.
    triggerSampleIndex : int
        Sample index where the trigger event occurred. This is only
        valid if triggering has been enabled. Set to 0 otherwise.
    triggerTimestamp : int
        Timestamp of the trigger event. This is only valid if
        triggering has been enabled. Set to 0 otherwise.
    filenames : strings
    acqStatus : int
        Acquisition status flags for the run interval. Individual bits
        are used as indicators as follows:
            Individual Internal Write Block Status (Bits 0-15, starting
            from LSB):
                Bits 0-15 indicate status for each internal write block,
                    so may not be very useful. Bits 16-31 indicate the
                    entire run status up to the time of query.
                Bit 0 : 1 = Input overrange.
                Bit 1 : 1 = USB data stream discontinuity.
                Bit 2 : 1 = Input buffer > 75% full (IQStream
                    processing heavily loaded).
                Bit 3 : 1 = Input buffer overflow (IQStream processing
                    overloaded, data loss has occurred).
                Bit 4 : 1 = Output buffer > 75% full (File output
                    falling behind writing data).
                Bit 5 : 1 = Output buffer overflow (File output too
                    slow, data loss has occurred).
                Bit 6 - Bit 15 : Unused, always 0.
            Entire Run Summary Status ("Sticky Bits"):
                The bits in this range are essentially the same as Bits
                    0-15, except once they are set (to 1) they remain
                    set for the entire run interval. They can be used to
                    determine if any of the status events occurred at
                    any time during the run.
                Bit 16 : 1 = Input overrange.
                Bit 17 : 1 = USB data stream discontinuity.
                Bit 18 : 1 = Input buffer > 75% full (IQStream
                    processing heavily loaded).
                Bit 19 : 1 = Input buffer overflow (IQStream processing
                    overloaded, data loss has occurred).
                Bit 20 : 1 = Output buffer > 75% full (File output
                    falling behind writing data).
                Bit 21 : 1 = Output buffer overflow (File output too
                    slow, data loss has occurred).
                Bit 22 - Bit 31 : Unused, always 0.
    """
    fileinfo = IQSTREAM_File_Info()
    err_check(rsa.IQSTREAM_GetDiskFileInfo(byref(fileinfo)))
    return fileinfo
        
def IQSTREAM_GetDiskFileWriteStatus():
    """
    Allow monitoring the progress of file output.

    The returned values indicate when the file output has started and
    completed. These become valid after IQSTREAM_Start() is called,
    with any file output destination selected.

    For untriggered configuration, isComplete is all that needs to be
    monitored. When it switches from false -> true, file output has
    completed. Note that if "infinite" file length is selected, then
    isComplete only changes to true when the run is stopped by running
    IQSTREAM_Stop().

    If triggering is used, isWriting can be used to determine when a
    trigger has been received. The client application can monitor this
    value, and if a maximum wait period has elapsed while it is still
    false, the output operation can be aborted. isWriting behaves the
    same for both finite and infinite file length settings.

    The [isComplete, isWriting] sequence is as follows (assumes a finite
    file length setting):
        Untriggered operation:
            IQSTREAM_Start()
                => File output in progress: [False, True]
                => File output complete: [True, True]
        Triggered operation:
            IQSTREAM_Start()
                => Waiting for trigger, file writing not started:
                    [False, False]
                => Trigger event detected, file writing in progress:
                    [False, True]
                => File output complete: [True, True]

    Returns
    -------
    bool: isComplete
        Whether the IQ stream file output writing is complete.
    bool: isWriting
        Whether the IQ stream processing has started writing to file.
    """
    isComplete = c_bool()
    isWriting = c_bool()
    err_check(rsa.IQSTREAM_GetDiskFileWriteStatus(byref(isComplete),
        byref(isWriting)))
    return isComplete.value, isWriting.value

def IQSTREAM_GetEnable():
    """
    Retrieve the current IQ stream processing state.

    Returns
    -------
    bool
        The current IQ stream processing enable status. True if active,
        False if inactive.
    """
    enabled = c_bool()
    err_check(rsa.IQSTREAM_GetEnable(byref(enabled)))
    return enabled.value

def IQSTREAM_GetIQDataBufferSize():
    """
    Get the maximum number of IQ sample pairs to be returned by IQSTREAM_GetData().

    Refer to the RSA API Reference Manual for additional details.

    Returns
    -------
    int
        Maximum size IQ output data buffer required when using client
        IQ access. Size value is in IQ sample pairs.
    """
    maxSize = c_int()
    err_check(rsa.IQSTREAM_GetIQDataBufferSize(byref(maxSize)))
    return maxSize.value

def IQSTREAM_SetAcqBandwidth(bwHz_req):
    """
    Request the acquisition bandwidth of the output IQ stream samples.

    The requested bandwidth should only be changed when the instrument
    is in the global stopped state. The new BW setting does not take
    effect until the global system state is cycled from stopped to
    running.

    The range of requested bandwidth values can be queried using
    IQSTREAM_GetMaxAcqBandwidth() and IQSTREAM_GetMinAcqBandwidth().

    The following table shows the mapping of requested bandwidth to
    output sample rate for all allowed bandwidth settings.

    Requested BW                      Output Sample Rate
    ----------------------------------------------------
    20.0 MHz < BW <= 40.0 MHz         56.000 MSa/s
    10.0 MHz < BW <= 20.0 MHz         28.000 MSa/s
    5.0 MHz < BW <= 10.0 MHz          14.000 MSa/s
    2.50 MHz < BW <= 5.0 MHz          7.000 MSa/s
    1.25 MHz < BW <= 2.50 MHz         3.500 MSa/s
    625.0 kHz < BW <= 1.25 MHz        1.750 MSa/s
    312.50 kHz < BW <= 625.0 kHz      875.000 kSa/s
    156.250 kHz < BW <= 312.50 kHz    437.500 kSa/s
    78125.0 Hz < BW <= 156.250 kHz    218.750 kSa/s
    39062.5 Hz < BW <= 78125.0 Hz     109.375 kSa/s
    19531.25 Hz < BW <= 39062.5 Hz    54687.5 Sa/s
    9765.625 Hz < BW <= 19531.25 Hz   24373.75 Sa/s
    BW <= 9765.625 Hz                 13671.875 Sa/s

    Parameters
    ----------
    bwHz_req : float or int
        Requested acquisition bandwidth of IQ streaming data, in Hz.
    """
    bwHz_req = check_num(bwHz_req)
    bwHz_req = check_range(bwHz_req, IQSTREAM_GetMinAcqBandwidth(),
        IQSTREAM_GetMaxAcqBandwidth())
    err_check(rsa.IQSTREAM_SetAcqBandwidth(c_double(bwHz_req)))

def IQSTREAM_SetDiskFileLength(msec):
    """
    Set the time length of IQ data written to an output file.

    See IQSTREAM_GetDiskFileWriteStatus to find out how to monitor file
    output status to determine when it is active and completed.

    Msec Value    File Store Behavior
    ----------------------------------------------------------------
    0             No time limit on file output. File storage is
                  terminated when IQSTREAM_Stop() is called.
    > 0           File output ends after this number of milliseconds
                  of samples stored. File storage can be terminated
                  early by calling IQSTREAM_Stop().

    Parameters
    ----------
    msec : int
        Length of time in milliseconds to record IQ samples to file.
    """
    msec = check_int(msec)
    msec = check_range(msec, 0, float('inf'))
    err_check(rsa.IQSTREAM_SetDiskFileLength(c_int(msec)))

def IQSTREAM_SetDiskFilenameBase(filenameBase):
    """
    Set the base filename for file output.

    Input can include the drive/path, as well as the common base
    filename portion of the file. It should not include a file
    extension, as the file writing operation will automatically append
    the appropriate one for the selected file format.

    The complete output filename has the format:
    <filenameBase><suffix><.ext>, where <filenameBase is set by this
    method, <suffix> is set by IQSTREAM_SetDiskFilenameSuffix(), and
    <.ext> is set by IQSTREAM_SetOutputConfiguration(). If separate data
    and header files are generated, the same path/filename is used for
    both, with different extensions to indicate the contents.

    Parameters
    ----------
    filenameBase : string
        Base filename for file output.
    """
    filenameBase = check_string(filenameBase)
    err_check(rsa.IQSTREAM_SetDiskFilenameBaseW(c_wchar_p(filenameBase)))

def IQSTREAM_SetDiskFilenameSuffix(suffixCtl):
    """
    Set the control that determines the appended filename suffix.

    suffixCtl Value    Suffix Generated
    -------------------------------------------------------------------
    -2                 None. Base filename is used without suffix. Note
                       that the output filename will not change automa-
                       tically from one run to the next, so each output
                       file will overwrite the previous one unless the
                       filename is explicitly changed by calling the
                       Set method again.
    -1                 String formed from file creation time. Format:
                       "-YYYY.MM.DD.hh.mm.ss.msec". Note this time is
                       not directly linked to the data timestamps, so
                       it should not be used as a high-accuracy time-
                       stamp of the file data!
    >= 0               5 digit auto-incrementing index, initial value =
                       suffixCtl. Format: "-nnnnn". Note index auto-
                       increments by 1 each time IQSTREAM_Start() is
                       invoked with file data destination setting.

    Parameters
    ----------
    suffixCtl : int
        The filename suffix control value.
    """
    suffixCtl = check_int(suffixCtl)
    suffixCtl = check_range(suffixCtl, -2, float('inf'))
    err_check(rsa.IQSTREAM_SetDiskFilenameSuffix(c_int(suffixCtl)))

def IQSTREAM_SetIQDataBufferSize(reqSize):
    """
    Set the requested size, in sample pairs, of the returned IQ record.

    Refer to the RSA API Reference Manual for additional details.

    Parameters
    ----------
    reqSize : int
        Requested size of IQ output data buffer in IQ sample pairs.
        0 resets to default.
    """
    reqSize = check_int(reqSize)
    err_check(rsa.IQSTREAM_SetIQDataBufferSize(c_int(reqSize)))

def IQSTREAM_SetOutputConfiguration(dest, dtype):
    """
    Set the output data destination and IQ data type.

    The destination can be the client application, or files of different
    formats. The IQ data type can be chosen independently of the file
    format. IQ data values are stored in interleaved I/Q/I/Q order
    regardless of the destination or data type.

    Note: TIQ format files only allow INT32 or INT16 data types.

    Note: Midas 2.0 format files (.cdif, .det extensions) are not
    implemented.

    Parameters
    ----------
    dest : string
        Destination (sink) for IQ sample output. Valid settings:
            CLIENT : Client application
            FILE_TIQ : TIQ format file (.tiq extension)
            FILE_SIQ : SIQ format file with header and data combined in
                one file (.siq extension)
            FILE_SIQ_SPLIT : SIQ format with header and data in separate
                files (.siqh and .siqd extensions)
    dtype : string
        Output IQ data type. Valid settings:
            SINGLE : 32-bit single precision floating point (not valid
                with TIQ file destination)
            INT32 : 32-bit integer
            INT16 : 16-bit integer
            SINGLE_SCALE_INT32 : 32-bit single precision float, with
                data scaled the same as INT32 data type (not valid with
                TIQ file destination)

    Raises
    ------
    RSA_Error
        If inputs are not valid settings, or if single data type is 
        selected along with TIQ file format.
    """
    dest = check_string(dest)
    dtype = check_string(dtype)
    if dest in IQSOUTDEST and dtype in IQSOUTDTYPE:
        if dest == "FILE_TIQ" and "SINGLE" in dtype:
            raise RSA_Error("Invalid selection of TIQ file with"
                + " single precision data type.")
        else:
            val1 = c_int(IQSOUTDEST.index(dest))
            val2 = c_int(IQSOUTDTYPE.index(dtype))
            err_check(rsa.IQSTREAM_SetOutputConfiguration(val1, val2))
    else:
        raise RSA_Error("Input data type or destination string invalid.")

def IQSTREAM_Start():
    """
    Initialize IQ stream processing and initiate data output.

    If the data destination is file, the output file is created, and if
    triggering is not enabled, data starts to be written to the file
    immediately. If triggering is enabled, data will not start to be
    written to the file until a trigger event is detected.
    TRIG_ForceTrigger() can be used to generate a trigger even if the
    specified one does not occur.

    If the data destination is the client application, data will become
    available soon after this method is called. Even if triggering is
    enabled, the data will begin flowing to the client without need for
    a trigger event. The client must begin retrieving data as soon
    after IQSTREAM_Start() as possible.
    """
    err_check(rsa.IQSTREAM_Start())

def IQSTREAM_Stop():
    """
    Terminate IQ stream processing and disable data output.

    If the data destination is file, file writing is stopped and the
    output file is closed.
    """
    err_check(rsa.IQSTREAM_Stop())

def IQSTREAM_WaitForIQDataReady(timeoutMsec):
    """
    Block while waiting for IQ Stream data output.

    This method blocks while waiting for the IQ Streaming processing to
    produce the next block of IQ data. If data becomes available during
    the timeout interval, the method returns True immediately. If the
    timeout interval expires without data being ready, the method
    returns False. A timeoutMsec value of 0 checks for data ready, and
    returns immediately without waiting.

    Parameters
    ----------
    timeoutMsec : int
        Timeout interval in milliseconds.

    Returns
    -------
    bool
        Ready status. True if data is ready, False if data not ready.
    """
    timeoutMsec = check_int(timeoutMsec)
    timeoutMsec = check_range(timeoutMsec, 0, float('inf'))
    ready = c_bool()
    err_check(rsa.IQSTREAM_WaitForIQDataReady(c_int(timeoutMsec),
        byref(ready)))
    return ready.value

""" SPECTRUM METHODS """

def SPECTRUM_AcquireTrace():
    """
    Initiate a spectrum trace acquisition.

    Before calling this method, all acquisition parameters must be set
    to valid states. These include center frequency, reference level,
    any desired trigger conditions, and the spectrum configuration
    settings.
    """
    err_check(rsa.SPECTRUM_AcquireTrace())

def SPECTRUM_GetEnable():
    """
    Return the spectrum measurement enable status.

    Returns
    -------
    bool
        True if spectrum measurement enabled, False if disabled.
    """
    enable = c_bool()
    err_check(rsa.SPECTRUM_GetEnable(byref(enable)))
    return enable.value

def SPECTRUM_GetLimits():
    """
    Return the limits of the spectrum settings.

    Returns
    -------
    Dict including the following:
    maxSpan : float
        Maximum span (device dependent).
    minSpan : float
        Minimum span.
    maxRBW : float
        Maximum resolution bandwidth.
    minRBW : float
        Minimum resolution bandwidth.
    maxVBW : float
        Maximum video bandwidth.
    minVBW : float
        Minimum video bandwidth.
    maxTraceLength : int
        Maximum trace length.
    minTraceLength : int
        Minimum trace length.
    """
    limits = SPECTRUM_LIMITS()
    err_check(rsa.SPECTRUM_GetLimits(byref(limits)))
    limits_dict = {'maxSpan' : limits.maxSpan,
        'minSpan' : limits.minSpan, 'maxRBW' : limits.maxRBW,
        'minRBW' : limits.minRBW, 'maxVBW' : limits.maxVBW,
        'minVBW' : limits.minVBW, 'maxTraceLength' : limits.maxTraceLength,
        'minTraceLength' : limits.minTraceLength
    }
    return limits_dict

def SPECTRUM_GetSettings():
    """
    Return the spectrum settings.

    In addition to user settings, this method also returns some
    internal setting values.

    Returns
    -------
    All of the following as a dict, in this order:
    span : float
        Span measured in Hz.
    rbw : float
        Resolution bandwidth measured in Hz.
    enableVBW : bool
        True for video bandwidth enabled, False for disabled.
    vbw : float
        Video bandwidth measured in Hz.
    traceLength : int
        Number of trace points.
    window : string
        Windowing method used for the transform.
    verticalUnit : string
        Vertical units.
    actualStartFreq : float
        Actual start frequency in Hz.
    actualStopFreq : float
        Actual stop frequency in Hz.
    actualFreqStepSize : float
        Actual frequency step size in Hz.
    actualRBW : float
        Actual resolution bandwidth in Hz.
    actualVBW : float
        Not used.
    actualNumIQSamples : int
        Actual number of IQ samples used for transform.
    """
    sets = SPECTRUM_SETTINGS()
    err_check(rsa.SPECTRUM_GetSettings(byref(sets)))
    settings_dict = {'span' : sets.span,
        'rbw' : sets.rbw,
        'enableVBW' : sets.enableVBW,
        'vbw' : sets.vbw,
        'traceLength' : sets.traceLength,
        'window' : SPECTRUM_WINDOWS[sets.window],
        'verticalUnit' : SPECTRUM_VERTICAL_UNITS[sets.verticalUnit],
        'actualStartFreq' : sets.actualStartFreq,
        'actualStopFreq' : sets.actualStopFreq,
        'actualFreqStepSize' : sets.actualFreqStepSize,
        'actualRBW' : sets.actualRBW,
        'actualVBW' : sets.actualVBW,
        'actualNumIQSamples' : sets.actualNumIQSamples}
    return settings_dict

def SPECTRUM_GetTrace(trace, maxTracePoints):
    """
    Return the spectrum trace data.

    Parameters
    ----------
    trace : str
        Selected trace. Must be 'Trace1', 'Trace2', or 'Trace3'.
    maxTracePoints : int
        Maximum number of trace points to retrieve. The traceData array
        should be at least this size.

    Returns
    -------
    traceData : float array
        Spectrum trace data, in the unit of verticalunit specified in
        the spectrum settings.
    outTracePoints : int
        Actual number of valid trace points in traceData array.

    Raises
    ------
    RSA_Error
        If the trace input does not match one of the valid strings.
    """
    trace = check_string(trace)
    maxTracePoints = check_int(maxTracePoints)
    if trace in SPECTRUM_TRACES:
        traceVal = c_int(SPECTRUM_TRACES.index(trace))
    else:
        raise RSA_Error("Invalid trace input.")
    traceData = (c_float * maxTracePoints)()
    outTracePoints = c_int()
    err_check(rsa.SPECTRUM_GetTrace(traceVal, c_int(maxTracePoints),
                                    byref(traceData), byref(outTracePoints)))
    return np.ctypeslib.as_array(traceData), outTracePoints.value

def SPECTRUM_GetTraceInfo():
    """
    Return the spectrum result information.

    Returns
    -------
    Dict including:
    timestamp : int
        Timestamp. See REFTIME_GetTimeFromTimestamp() for converting
        from timestamp to time.
    acqDataStatus : int
        1 for adcOverrange, 2 for refFreqUnlock, and 32 for adcDataLost.
    """
    traceInfo = SPECTRUM_TRACEINFO()
    err_check(rsa.SPECTRUM_GetTraceInfo(byref(traceInfo)))
    info_dict = { 'timestamp' : traceInfo.timestamp,
            'acqDataStatus' : traceInfo.acqDataStatus}
    return info_dict

def SPECTRUM_GetTraceType(trace):
    """
    Query the trace settings.

    Parameters
    ----------
    trace : str
        Desired trace. Must be 'Trace1', 'Trace2', or 'Trace3'.

    Returns
    -------
    enable : bool
        Trace enable status. True for enabled, False for disabled.
    detector : string
        Detector type. Valid results are:
            PosPeak, NegPeak, AverageVRMS, or Sample.

    Raises
    ------
    RSA_Error
        If the trace input does not match a valid setting.
    """
    trace = check_string(trace)
    if trace in SPECTRUM_TRACES:
        traceVal = c_int(SPECTRUM_TRACES.index(trace))
    else:
        raise RSA_Error("Invalid trace input.")
    enable = c_bool()
    detector = c_int()
    err_check(rsa.SPECTRUM_GetTraceType(traceVal, byref(enable), byref(detector)))
    return enable.value, SPECTRUM_DETECTORS[detector.value]

def SPECTRUM_SetDefault():
    """
    Set the spectrum settings to their default values.

    This does not change the spectrum enable status. The following are
    the default settings:
        Span : 40 MHz
        RBW : 300 kHz
        Enable VBW : False
        VBW : 300 kHz
        Trace Length : 801
        Window : Kaiser
        Vertical Unit : dBm
        Trace 0 : Enable, +Peak
        Trace 1 : Disable, -Peak
        Trace 2 : Disable, Average
    """
    err_check(rsa.SPECTRUM_SetDefault())

def SPECTRUM_SetEnable(enable):
    """
    Set the spectrum enable status.

    When the spectrum measurement is enabled, the IQ acquisition is
    disabled.

    Parameters
    ----------
    enable : bool
        True enables the spectrum measurement. False disables it.
    """
    enable = check_bool(enable)
    err_check(rsa.SPECTRUM_SetEnable(c_bool(enable)))

def SPECTRUM_SetSettings(span, rbw, enableVBW, vbw, traceLen, win, vertUnit):
    """
    Set the spectrum settings.

    Parameters
    ----------
    span : float
        Span measured in Hz.
    rbw : float
        Resolution bandwidth measured in Hz.
    enableVBW : bool
        True for video bandwidth enabled, False for disabled.
    vbw : float
        Video bandwidth measured in Hz.
    traceLen : int
        Number of trace points.
    win : string
        Windowing method used for the transform. Valid settings:
        Kaiser, Mil6dB, BlackmanHarris, Rectangular, FlatTop, or Hann.
    vertUnit : string
        Vertical units. Valid settings: dBm, Watt, Volt, Amp, or dBmV.

    Raises
    ------
    RSA_Error
        If window or verticalUnit string inputs are not one of the
        allowed settings.
    """
    win = check_string(win)
    vertUnit = check_string(vertUnit)
    if win in SPECTRUM_WINDOWS and vertUnit in SPECTRUM_VERTICAL_UNITS:
        settings = SPECTRUM_SETTINGS()
        settings.span = check_num(span)
        settings.rbw = check_num(rbw)
        settings.enableVBW = check_bool(enableVBW)
        settings.vbw = check_num(vbw)
        settings.traceLength = check_int(traceLen)
        settings.window = SPECTRUM_WINDOWS.index(win)
        settings.verticalUnit = SPECTRUM_VERTICAL_UNITS.index(vertUnit)
        err_check(rsa.SPECTRUM_SetSettings(settings))
    else:
        raise RSA_Error("Window or vertical unit input invalid.")

def SPECTRUM_SetTraceType(trace="Trace1", enable=True, detector='AverageVRMS'):
    """
    Set the trace settings.

    Parameters
    ----------
    trace : str
        One of the spectrum traces. Can be 'Trace1', 'Trace2', or 'Trace3'.
        Set to Trace1 by default.
    enable : bool
        True enables trace output. False disables it. True by default.
    detector : string
        Detector type. Default to AverageVRMS. Valid settings:
            PosPeak, NegPeak, AverageVRMS, or Sample.

    Raises
    ------
    RSA_Error
        If the trace or detector type input is not one of the valid settings.
    """
    trace = check_string(trace)
    detector = check_string(detector)
    if trace in SPECTRUM_TRACES and detector in SPECTRUM_DETECTORS:
        traceVal = c_int(SPECTRUM_TRACES.index(trace))
        detVal = c_int(SPECTRUM_DETECTORS.index(detector))
        err_check(rsa.SPECTRUM_SetTraceType(traceVal, c_bool(enable), detVal))
    else:
        raise RSA_Error("Trace or detectory type input invalid.")

def SPECTRUM_WaitForTraceReady(timeoutMsec):
    """
    Wait for the spectrum trace data to be ready to be queried.

    Parameters
    ----------
    timeoutMsec : int
        Timeout value in msec.

    Returns
    -------
    bool
        True indicates spectrum trace data is ready for acquisition.
        False indicates it is not ready, and timeout value is exceeded.
    """
    timeoutMsec = check_int(timeoutMsec)
    ready = c_bool()
    err_check(rsa.SPECTRUM_WaitForTraceReady(c_int(timeoutMsec),
                                             byref(ready)))
    return ready.value

""" TIME METHODS """

def REFTIME_SetReferenceTime(refTimeSec, refTimeNsec, refTimestamp):
    """
    Set the RSA API time system association.

    This method sets the RSA API time system association between a
    "wall-clock" time value and the internal timestamp counter. The
    wall-clock time is composed of refTimeSec + refTimeNsec, which
    specify a UTC time to nanosecond precision.

    At device connection, the API automatically initializes the time
    system using this method to associate current OS time with the
    current value of the timestamp counter. This setting does not give
    high-accuracy time alignment due to the uncertainty in the OS time,
    but provides a basic time/timestamp association. The REFTIME
    methods then use this association for time calculations. To re-
    initialize the time system this way some time after connection,
    call the method with all arguments equal to 0.

    If a higher-precision time reference is available, such as GPS or
    GNSS receiver with 1PPS pulse output, or other precisely known time
    event, the API time system can be aligned to it by capturing the
    timestamp count of the event using the External trigger input. Then
    the timestamp value and corresponding wall-time value (sec+nsec)
    are associated using this method. This provides timestamp
    accuracy as good as the accuracy of the time + event alignment.

    If the user application calls this method to set the time
    reference, the REFTIME_GetReferenceTimeSource() method will return
    USER status.

    Parameters
    ----------
    refTimeSec : int
        Seconds component of time system wall-clock reference time.
        Format is number of seconds elapsed since midnight (00:00:00),
        Jan 1, 1970, UTC.
    refTimeNsec : int
        Nanosecond component of time system wall-clock reference time.
        Format is number of integer nanoseconds within the second
        specified in refTimeSec.
    refTimestamp : int
        Timestamp counter component of time system reference time.
        Format is the integer timestamp count corresponding to the time
        specified by refTimeSec + refTimeNsec.
    """
    refTimeSec = check_int(refTimeSec)
    refTimeNsec = check_int(refTimeNsec)
    refTimestamp = check_int(refTimestamp)
    err_check(rsa.REFTIME_SetReferenceTime(c_uint64(refTimeSec),
                                           c_uint64(refTimeNsec),
                                           c_uint64(refTimestamp)))

def REFTIME_GetReferenceTime():
    """
    Query the RSA API system time association.

    The refTimeSec value is the number of seconds elapsed since
    midnight (00:00:00), Jan 1, 1970, UTC.

    The refTimeNsec value is the number of nanoseconds offset into the
    refTimeSec second. refTimestamp is the timestamp counter value.
    These values are initially set automatically by the API system
    using OS time, but may be modified by the REFTIME_SetReferenceTime()
    method if a better reference time source is available.

    Returns
    -------
    refTimeSec : int
        Seconds component of reference time association.
    refTimeNsec : int
        Nanosecond component of reference time association.
    refTimestamp : int
        Counter timestamp of reference time association.
    """
    refTimeSec = c_uint64()
    refTimeNsec = c_uint64()
    refTimestamp = c_uint64()
    err_check(rsa.REFTIME_GetReferenceTime(byref(refTimeSec),
                                           byref(refTimeNsec),
                                           byref(refTimestamp)))
    return refTimeSec.value, refTimeNsec.value, refTimestamp.value

def REFTIME_GetCurrentTime():
    """
    Return the current RSA API system time.

    Returns second and nanosecond components, along with the
    corresponding current timestamp value.

    The o_TimeSec value is the number of seconds elapsed since midnight
    (00:00:00), Jan 1, 1970, UTC. The o_timeNsec value is the number of
    nanoseconds offset into the specified second. The time and
    timestamp values are accurately aligned with each other at the time
    of the method call.

    Returns
    -------
    o_timeSec : int
        Seconds component of current time.
    o_timeNsec : int
        Nanoseconds component of current time.
    o_timestamp : int
        Timestamp of current time.
    """
    o_timeSec = c_uint64()
    o_timeNsec = c_uint64()
    o_timestamp = c_uint64()
    err_check(rsa.REFTIME_GetCurrentTime(byref(o_timeSec), byref(o_timeNsec),
                                         byref(o_timestamp)))
    return o_timeSec.value, o_timeNsec.value, o_timestamp.value

def REFTIME_GetIntervalSinceRefTimeSet():
    """
    Return num. of sec's elapsed since time/timestamp association set.

    Returns
    -------
    float
        Seconds since the internal reference time/timestamp association
        was last set.
    """
    sec = c_double()
    err_check(rsa.REFTIME_GetIntervalSinceRefTimeSet(byref(sec)))
    return sec.value

def REFTIME_GetReferenceTimeSource():
    """
    Query the API time reference alignment source.

    Returns
    -------
    string
        Current time reference source. Valid results:
            NONE, SYSTEM, GNSS, or USER.
    """
    srcVal = c_int()
    err_check(rsa.REFTIME_GetReferenceTimeSource(byref(srcVal)))
    return REFTIME_SRC[srcVal.value]

def REFTIME_GetTimeFromTimestamp(i_timestamp):
    """
    Convert timestamp into equivalent time using current reference.

    Parameters
    ----------
    i_timestamp : int
        Timestamp counter time to convert to time values.

    Returns
    -------
    o_timeSec : int
        Time value seconds component.
    o_timeNsec : int
        Time value nanoseconds component.
    """
    i_timestamp = check_int(i_timestamp)
    o_timeSec = c_uint64()
    o_timeNsec = c_uint64()
    err_check(rsa.REFTIME_GetTimeFromTimestamp(c_uint64(i_timestamp),
                                               byref(o_timeSec),
                                               byref(o_timeNsec)))
    return o_timeSec.value, o_timeNsec.value

def REFTIME_GetTimestampFromTime(i_timeSec, i_timeNsec):
    """
    Convert time into equivalent timestamp using current reference.

    Parameters
    ----------
    i_timeSec : int
        Seconds component to convert to timestamp.
    i_timeNsec : int
        Nanoseconds component to convert to timestamp.

    Returns
    -------
    int
        Equivalent timestamp value.
    """
    i_timeSec = check_int(i_timeSec)
    i_timeNsec = check_int(i_timeNsec)
    o_timestamp = c_uint64()    
    err_check(rsa.REFTIME_GetTimestampFromTime(c_uint64(i_timeSec),
                                               c_uint64(i_timeNsec),
                                               byref(o_timestamp)))
    return o_timestamp.value

def REFTIME_GetTimestampRate():
    """
    Return clock rate of the countinuously running timestamp counter.

    This method can be used for calculations on timestamp values.

    Returns
    -------
    int
        Timestamp counter clock rate.
    """
    refTimestampRate = c_uint64()
    err_check(rsa.REFTIME_GetTimestampRate(byref(refTimestampRate)))
    return refTimestampRate.value

""" TRIGGER METHODS """

def TRIG_ForceTrigger():
    """Force the device to trigger."""
    err_check(rsa.TRIG_ForceTrigger())

def TRIG_GetIFPowerTriggerLevel():
    """
    Return the trigger power level.

    Returns
    -------
    float
        Detection power level for the IF power trigger source
    """
    level = c_double()
    err_check(rsa.TRIG_GetIFPowerTriggerLevel(byref(level)))
    return level.value

def TRIG_GetTriggerMode():
    """
    Return the trigger mode (either freeRun or triggered).

    When the mode is set to freeRun, the signal is continually updated.

    When the mode is set to Triggered, the data is only updated when a trigger occurs.

    Returns
    -------
    string
        Either "freeRun" or "Triggered".
    """
    mode = c_int()
    err_check(rsa.TRIG_GetTriggerMode(byref(mode)))
    return TRIGGER_MODE[mode.value]

def TRIG_GetTriggerPositionPercent():
    """
    Return the trigger position percent.

    Note: The trigger position setting only affects IQ Block and
    Spectrum acquisitions.

    Returns
    -------
    float
        Trigger position percent value when the method completes.
    """
    trigPosPercent = c_double()
    err_check(rsa.TRIG_GetTriggerPositionPercent(byref(trigPosPercent)))
    return trigPosPercent.value

def TRIG_GetTriggerSource():
    """
    Return the trigger source.

    When set to external, acquisition triggering looks at the external
    trigger input for a trigger signal. When set to IF power level, the
    power of the signal itself causes a trigger to occur.

    Returns
    -------
    string
        The trigger source type. Valid results:
            External : External source.
            IFPowerLevel : IF power level source.
    """
    source = c_int()
    err_check(rsa.TRIG_GetTriggerSource(byref(source)))
    return TRIGGER_SOURCE[source.value]

def TRIG_GetTriggerTransition():
    """
    Return the current trigger transition mode.

    Returns
    -------
    string
        Name of the trigger transition mode. Valid results:
            LH : Trigger on low-to-high input level change.
            HL : Trigger on high-to-low input level change.
            Either : Trigger on either LH or HL transitions.
    """
    transition = c_int()
    err_check(rsa.TRIG_GetTriggerTransition(byref(transition)))
    return TRIGGER_TRANSITION[transition.value]

def TRIG_SetIFPowerTriggerLevel(level):
    """
    Set the IF power detection level.

    When set to the IF power level trigger source, a trigger occurs
    when the signal power level crosses this detection level.

    Parameters
     ----------
    level : float
        The detection power level setting for the IF power trigger
        source.
    """
    level = check_num(level)
    level = check_range(level, -130, 30)
    err_check(rsa.TRIG_SetIFPowerTriggerLevel(c_double(level)))

def TRIG_SetTriggerMode(mode):
    """
    Set the trigger mode.

    Parameters
    ----------
    mode : string
        The trigger mode. Valid settings:
            freeRun : to continually gather data
            Triggered : do not acquire new data unless triggered

    Raises
    ------
    RSA_Error
        If the input string is not one of the valid settings.
    """
    mode = check_string(mode)
    if mode in TRIGGER_MODE:
        modeValue = TRIGGER_MODE.index(mode)
        err_check(rsa.TRIG_SetTriggerMode(c_int(modeValue)))
    else:
        raise RSA_Error("Invalid trigger mode input string.")

def TRIG_SetTriggerPositionPercent(trigPosPercent):
    """
    Set the trigger position percentage.

    This value determines how much data to store before and after a 
    trigger event. The stored data is used to update the signal's image
    when a trigger occurs. The trigger position setting only affects IQ
    Block and Spectrum acquisitions.

    Default setting is 50%.

    Parameters
    ----------
    trigPosPercent : float
        The trigger position percentage, from 1% to 99%.
    """
    trigPosPercent = check_num(trigPosPercent)
    trigPosPercent = check_range(trigPosPercent, 1, 99)
    err_check(rsa.TRIG_SetTriggerPositionPercent(c_double(trigPosPercent)))

def TRIG_SetTriggerSource(source):
    """
    Set the trigger source.

    Parameters
    ----------
    source : string
        A trigger source type. Valid settings:
            External : External source.
            IFPowerLevel: IF power level source.

    Raises
    ------
    RSA_Error
        If the input string does not match one of the valid settings.
    """
    source = check_string(source)
    if source in TRIGGER_SOURCE:
        sourceValue = TRIGGER_SOURCE.index(source)
        err_check(rsa.TRIG_SetTriggerSource(c_int(sourceValue)))
    else:
        raise RSA_Error("Invalid trigger source input string.")

def TRIG_SetTriggerTransition(transition):
    """
    Set the trigger transition detection mode.

    Parameters
    ----------
    transition : string
        A trigger transition mode. Valid settings:
            LH : Trigger on low-to-high input level change.
            HL : Trigger on high-to-low input level change.
            Either : Trigger on either LH or HL transitions.

    Raises
    ------
    RSA_Error
        If the input string does not match one of the valid settings.
    """
    transition = check_string(transition)
    if transition in TRIGGER_TRANSITION:
        transValue = TRIGGER_TRANSITION.index(transition)
        err_check(rsa.TRIG_SetTriggerTransition(c_int(transValue)))
    else:
        raise RSA_Error("Invalid trigger transition mode input string.")

""" HELPER METHODS """

def DEVICE_SearchAndConnect(verbose=False):
    """
    Search for and connect to a Tektronix RSA device. 
    
    More than 10 devices cannot be found at once. Connection only
    occurs if exactly one device is found. It may be more convenient to
    simply use DEVICE_Connect(), however this helper method is useful
    if problems occur when searching for or connecting to a device. 

    Parameters
    ----------
    verbose : bool
        Whether to print the steps of the process as they happen.

    Raises
    ------
    RSA_Error
        If no matching device is found, if more than one matching
        device are found, or if connection fails.
    """
    if verbose:
        print("Searching for devices...")

    foundDevices = DEVICE_Search()
    numFound = len(foundDevices)

    if numFound == 1:
        foundDevString = "The following device was found:"
    elif numFound > 1:
        foundDevString = "The following devices were found:"
    for (ID, key) in foundDevices.items():
        foundDevString += '\r\n{}'.format(str(ID) + ': ' + str(key))

    if verbose:
        print("Device search completed.\n")
        print(foundDevString + '\n')

    # Zero devices found case handled within DEVICE_Search()
    # Multiple devices found case:
    if numFound > 1:
        raise RSA_Error("Found {} devices, need exactly 1.".format(numFound))
    else:
        if verbose:
            print("Connecting to device...")
        DEVICE_Connect()
        if verbose:
            print("Device connected.\n")

def IQSTREAM_Tempfile(cf, refLevel, bw, durationMsec):
    """
    Retrieve IQ data from device by first writing to a tempfile.

    Parameters
    ----------
    cf : float or int
        Center frequency value in Hz.
    refLevel : float or int
        Reference level value in dBm.
    bw : float or int
        Requested IQ streaming bandwidth in Hz.
    durationMsec : int
        Duration of time to record IQ data, in milliseconds.

    Returns
    -------
    Numpy array of np.complex64 values
        IQ data, with each element in the form (I + j*Q)
    """
    # Configuration parameters
    dest=IQSOUTDEST[3] # Split SIQ format
    dType=IQSOUTDTYPE[0] # 32-bit single precision floating point
    suffixCtl=-2 # No file suffix
    filename = 'tempIQ'
    sleepTimeSec = 0.1 # Loop sleep time checking if acquisition complete

    # Ensure device is stopped before proceeding
    DEVICE_Stop()

    # Create temp directory and configure/collect data
    with tempfile.TemporaryDirectory() as tmpDir:
        filenameBase = tmpDir + '/' + filename

        # Configure device
        CONFIG_SetCenterFreq(cf)
        CONFIG_SetReferenceLevel(refLevel)
        IQSTREAM_SetAcqBandwidth(bw)
        IQSTREAM_SetOutputConfiguration(dest, dType)
        IQSTREAM_SetDiskFilenameBase(filenameBase)
        IQSTREAM_SetDiskFilenameSuffix(suffixCtl)
        IQSTREAM_SetDiskFileLength(durationMsec)
        IQSTREAM_ClearAcqStatus()

        # Collect data
        complete = False
        writing = False

        DEVICE_Run()
        IQSTREAM_Start()
        while not complete:
            sleep(sleepTimeSec)
            (complete, writing) = IQSTREAM_GetDiskFileWriteStatus()
        IQSTREAM_Stop()

        # Check acquisition status
        fileInfo = IQSTREAM_GetDiskFileInfo()
        IQSTREAM_StatusParser(fileInfo)

        DEVICE_Stop()

        # Read data back in from file
        with open(filenameBase + '.siqd', 'rb') as f:
            # if siq file, skip header
            if f.name[-1] == 'q':
                # this case currently is never used
                # but would be needed if code is later modified
                f.seek(1024)
            # read in data as float32 ("SINGLE" SIQ)
            d = np.frombuffer(f.read(), dtype=np.float32)

    # Deinterleave I and Q
    i = d[0:-1:2]
    q = np.append(d[1:-1:2], d[-1])
    # Re-interleave as numpy complex64)
    iqData = i + 1j*q

    return iqData

def IQSTREAM_StatusParser(iqStreamInfo):
    """
    Parse IQSTREAM_File_Info structure.

    Parameters
    ----------
    iqStreamInfo : IQSTREAM_File_Info
        The IQ streaming status information structure.

    Raises
    ------
    RSA_Error
        If errors have occurred during IQ streaming.
    """
    status = iqStreamInfo.acqStatus
    if status == 0:
        pass
    elif bool(status & 0x10000):  # mask bit 16
        raise RSA_Error('Input overrange.')
    elif bool(status & 0x40000):  # mask bit 18
        raise RSA_Error('Input buffer > 75{} full.'.format('%'))
    elif bool(status & 0x80000):  # mask bit 19
        raise RSA_Error('Input buffer overflow. IQStream processing too'
              + ' slow, data loss has occurred.')
    elif bool(status & 0x100000):  # mask bit 20
        raise RSA_Error('Output buffer > 75{} full.'.format('%'))
    elif bool(status & 0x200000):  # mask bit 21
        raise RSA_Error('Output buffer overflow. File writing too slow, '
            + 'data loss has occurred.')       

def SPECTRUM_Acquire(trace='Trace1', tracePoints=801, timeoutMsec=10):
    """
    Acquire spectrum trace.

    Parameters
    ----------
    trace : str
        Desired spectrum trace. Valid settings:
        'Trace1', 'Trace2', or 'Trace3'
    tracePoints : int
        Maximum number of trace points to receive.
    timeoutMsec : int
        How long to wait for trace data to be ready, in milliseconds.

    Returns
    -------
    traceData : float array
        Spectrum trace data, in the unit of verticalunit specified in
        the spectrum settings.
    outTracePoints : int
        Actual number of valid trace points in traceData array.
    """
    DEVICE_Run()
    SPECTRUM_AcquireTrace()
    while not SPECTRUM_WaitForTraceReady(timeoutMsec):
        pass
    return SPECTRUM_GetTrace(trace, tracePoints)

def IQBLK_Configure(cf=1e9, refLevel=0, iqBw=40e6, recordLength=1024):
    """
    Configure device for IQ block collection.

    Parameters
    ----------
    cf : float or int
        Desired center frequency in Hz.
    refLevel : float or int
        Desired reference level in dBm.
    iqBw : float or int
        Desired IQ bandwidth in Hz.
    recordLength : int
        Desired IQBLK record length, a number of samples.
    """
    CONFIG_SetCenterFreq(cf)
    CONFIG_SetReferenceLevel(refLevel)
    IQBLK_SetIQBandwidth(iqBw)
    IQBLK_SetIQRecordLength(recordLength)

def IQBLK_Acquire(func=IQBLK_GetIQDataDeinterleaved, recLen=1024, tOutMs=10):
    """
    Acquire IQBLK data using selected method.

    Parameters
    ----------
    func : method
        Desired IQBLK acquisition method. Can be either IQBLK_GetIQData
        or IQBLK_GetIQDataDeinterleaved, depending on desired format.
    recLen : int
        IQBLK record length, a number of samples.
    tOutMs : int
        How long to wait for IQBLK data to be ready, in milliseconds.

    Returns
    -------
    iqData : 1 or 2 numpy arrays
        Returned IQ samples, formatted as determined by func selection.
    """
    DEVICE_Run()
    IQBLK_AcquireIQData()
    while not IQBLK_WaitForIQDataReady(tOutMs):
        pass
    return func(recLen)

def AUDIO_Acquire(inSize=1000, mode=3):
    DEVICE_Run()
    AUDIO_SetMode(mode)
    AUDIO_Start()
    if AUDIO_GetEnable():
        data = AUDIO_GetData(inSize)
    else:
        raise RSA_Error("Audio mode not enabled after starting.")
    AUDIO_Stop()
    return data