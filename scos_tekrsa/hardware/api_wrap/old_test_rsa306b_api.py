import numpy as np
import unittest
from os.path import isdir
from os import mkdir
from scos_tekrsa.hardware.api_wrap.rsa306b_api import *
from time import sleep

"""
This is a test for the entire API Wrapper for the Tektronix RSA306B.
It requires a compatible RSA device to be connected.
"""

class rsa_api_test(unittest.TestCase):
    """Test for rsa306b_api.py"""

    """ALIGN Command Testing"""

    def test_ALIGN_GetAlignmentNeeded(self):
        self.assertIsInstance(ALIGN_GetAlignmentNeeded(), bool)
    
    def test_ALIGN_GetWarmupStatus(self):
        self.assertIsInstance(ALIGN_GetWarmupStatus(), bool)
    
    def test_ALIGN_RunAlignment(self):
        self.assertIsNone(ALIGN_RunAlignment())

    """AUDIO Command Testing"""

    def test_AUDIO_FrequencyOffset(self):
        freq = 437e3
        self.assertIsNone(AUDIO_SetFrequencyOffset(freq))
        self.assertEqual(AUDIO_GetFrequencyOffset(), freq)
        
        self.assertRaises(ValueError, AUDIO_SetFrequencyOffset, 21e6)
        self.assertRaises(ValueError, AUDIO_SetFrequencyOffset, -21e6)
        self.assertRaises(TypeError, AUDIO_SetFrequencyOffset, 'abc')
        self.assertRaises(TypeError, AUDIO_SetFrequencyOffset, [num])
    
    def test_AUDIO_GetEnable(self):
        self.assertIsInstance(AUDIO_GetEnable(), bool)

    def test_AUDIO_Mode(self):
        for mode in range(6):
            self.assertIsNone(AUDIO_SetMode(mode))
            self.assertEqual(AUDIO_GetMode(), mode)
        
        self.assertRaises(TypeError, AUDIO_SetMode, 'abc')
        self.assertRaises(ValueError, AUDIO_SetMode, num)
        self.assertRaises(ValueError, AUDIO_SetMode, neg)
    
    def test_AUDIO_Volume(self):
        vol = 0.75
        self.assertIsNone(AUDIO_SetVolume(vol))
        self.assertEqual(AUDIO_GetVolume(), vol)
        self.assertIsInstance(AUDIO_GetVolume(), float)
        self.assertRaises(TypeError, AUDIO_SetVolume, 'abc')
        self.assertRaises(ValueError, AUDIO_SetVolume, num)
        self.assertRaises(ValueError, AUDIO_SetVolume, neg)
    
    def test_AUDIO_Mute(self):
        mute = [False, True]
        for m in mute:
            self.assertIsNone(AUDIO_SetMute(m))
            self.assertEqual(AUDIO_GetMute(), m)
            self.assertIsInstance(AUDIO_GetMute(), bool)
        
        self.assertRaises(TypeError, AUDIO_SetMute, 'abc')
        self.assertRaises(TypeError, AUDIO_SetMute, neg)
        self.assertRaises(TypeError, AUDIO_SetMute, num)
    
    def test_AUDIO_StartStop(self):
        self.assertIsNone(AUDIO_Start())
        self.assertIsNone(AUDIO_Stop())

    def test_AUDIO_Acquire(self):
        inSize = 500
        mode = 3
        self.assertIsInstance(AUDIO_Acquire(inSize, mode), np.ndarray)
        self.assertRaises(TypeError, AUDIO_Acquire, inSize, 'abc')
        self.assertRaises(TypeError, AUDIO_Acquire, 'abc', mode)
        self.assertRaises(ValueError, AUDIO_Acquire, inSize, neg)
        self.assertRaises(ValueError, AUDIO_Acquire, neg, mode)

    """CONFIG Command Testing"""
    
    def test_CONFIG_CenterFreq(self):
        cf = 2.4453e9
        self.assertIsNone(CONFIG_SetCenterFreq(cf))
        self.assertEqual(CONFIG_GetCenterFreq(), cf)
        
        self.assertRaises(TypeError, CONFIG_SetCenterFreq, 'abc')
        self.assertRaises(TypeError, CONFIG_SetCenterFreq, False)
        self.assertRaises(ValueError, CONFIG_SetCenterFreq, 400e9)
        self.assertRaises(ValueError, CONFIG_SetCenterFreq, -40e6)

    """
    # The following test requires an external reference to be in use.
    def test_CONFIG_ExternalRef(self):
        self.assertIsNone(CONFIG_SetExternalRefEnable(exRefEn=True))
        self.assertTrue(CONFIG_GetExternalRefEnable())
        extRefFreq = 10e6
        self.assertEqual(CONFIG_GetExternalRefFrequency(), extRefFreq)
        CONFIG_SetExternalRefEnable(exRefEn=False)
        self.assertRaises(RSA_Error, CONFIG_GetExternalRefFrequency)
    """

    def test_CONFIG_FrequencyReferenceSource(self):
        self.assertRaises(RSA_Error, CONFIG_SetFrequencyReferenceSource, 'GNSS')
        self.assertRaises(RSA_Error, CONFIG_SetFrequencyReferenceSource, 'abc')
        self.assertRaises(TypeError, CONFIG_SetFrequencyReferenceSource, 0)
        self.assertIsNone(CONFIG_SetFrequencyReferenceSource('INTERNAL'))
        self.assertIsInstance(CONFIG_GetFrequencyReferenceSource(), str)


    def test_CONFIG_Preset(self):
        self.assertIsNone(CONFIG_Preset())
        self.assertEqual(CONFIG_GetCenterFreq(), 1.5e9)
        self.assertEqual(CONFIG_GetReferenceLevel(), 0)
        self.assertEqual(IQBLK_GetIQBandwidth(), 40e6)
        self.assertEqual(IQBLK_GetIQRecordLength(), 1024)
    
    def test_CONFIG_ReferenceLevel(self):
        refLevel = 17
        self.assertIsNone(CONFIG_SetReferenceLevel(refLevel))
        self.assertEqual(CONFIG_GetReferenceLevel(), refLevel)
        self.assertRaises(TypeError, CONFIG_SetReferenceLevel, 'abc')
        self.assertRaises(ValueError, CONFIG_SetReferenceLevel, 31)
        self.assertRaises(ValueError, CONFIG_SetReferenceLevel, -131)
    
    def test_CONFIG_GetMaxCenterFreq(self):
        maxCf = 6.2e9
        self.assertEqual(CONFIG_GetMaxCenterFreq(), maxCf)
    
    def test_CONFIG_GetMinCenterFreq(self):
        minCf = 9e3
        self.assertEqual(CONFIG_GetMinCenterFreq(), minCf)

    """DEVICE Command Testing"""

    def test_DEVICE_Connect(self):
        # Stop and disconnect device first
        DEVICE_Stop()
        self.assertIsNone(DEVICE_Disconnect())
        self.assertRaises(TypeError, DEVICE_Connect, 'abc')
        self.assertRaises(ValueError, DEVICE_Connect, neg)
        self.assertIsNone(DEVICE_Connect(0))

    def test_DEVICE_PrepareForRun(self):
        self.assertIsNone(DEVICE_PrepareForRun())
    
    def test_DEVICE_Run(self):
        self.assertIsNone(DEVICE_Run())
        self.assertTrue(DEVICE_GetEnable())
    
    def test_DEVICE_Stop(self):
        self.assertIsNone(DEVICE_Stop())
        self.assertFalse(DEVICE_GetEnable())
    
    def test_DEVICE_GetEventStatus_no_signal(self):
        eventType = ['OVERRANGE', 'TRIGGER', '1PPS']
        for e in eventType:
            event, timestamp = DEVICE_GetEventStatus(e)
            self.assertFalse(event)
            self.assertEqual(timestamp, 0)
        self.assertRaises(TypeError, DEVICE_GetEventStatus, 0)
        self.assertRaises(RSA_Error, DEVICE_GetEventStatus, 'abc')
    
    def test_DEVICE_GetEventStatus_trig_event(self):
        DEVICE_Run()
        TRIG_ForceTrigger()
        sleep(0.05)
        trig, trigTs = DEVICE_GetEventStatus('TRIGGER')
        self.assertTrue(trig)
        self.assertGreater(trigTs, 0)
    
    """
    # The following test woudl require an actual overrange event.
    def test_DEVICE_GetEventStatus_overrange(self):
        pass
    """

    def test_DEVICE_GetOverTemperatureStatus(self):
        self.assertIsInstance(DEVICE_GetOverTemperatureStatus(), bool)
        self.assertEqual(DEVICE_GetOverTemperatureStatus(), False)

    def test_DEVICE_GetNomenclature_rsa306b(self):
        self.assertEqual(DEVICE_GetNomenclature(), 'RSA306B')

    def test_DEVICE_GetSerialNumber(self):
        sn = DEVICE_GetSerialNumber()
        self.assertIsInstance(sn, str)
        self.assertEqual(len(sn), 7)

    def test_DEVICE_GetAPIVersion(self):
        # This uses the Linux API version number
        self.assertEqual(DEVICE_GetAPIVersion(), '1.0.0014')

    def test_DEVICE_GetFWVersion(self):
        self.assertEqual(DEVICE_GetFWVersion(), 'V1.7')

    def test_DEVICE_GetFPGAVersion(self):
        self.assertEqual(DEVICE_GetFPGAVersion(), 'V2.1')

    def test_DEVICE_GetHWVersion(self):
        self.assertEqual(DEVICE_GetHWVersion(), 'V7')

    def test_DEVICE_GetInfo(self):
        info = DEVICE_GetInfo()
        self.assertIsInstance(info, dict)
        self.assertEqual(len(info), 6)
        self.assertEqual(len(info['serialNum']), 7)
        self.assertEqual(info['apiVersion'], '1.0.0014')
        self.assertEqual(info['fwVersion'], 'V1.7')
        self.assertEqual(info['fpgaVersion'], 'V2.1')
        self.assertEqual(info['hwVersion'], 'V7')

    """GNSS Command Testing"""
    
    def test_GNSS_GetHwInstalled(self):
        self.assertFalse(GNSS_GetHwInstalled())

    """IQBLK Command Testing"""
    
    def test_IQBLK_MinMaxIQBandwidth(self):
        maxBw = IQBLK_GetMaxIQBandwidth()
        minBw = IQBLK_GetMinIQBandwidth()
        IQBLK_SetIQBandwidth(maxBw) # To get maxRl properly
        maxRl = IQBLK_GetMaxIQRecordLength()
        self.assertEqual(maxBw, 40e6)
        self.assertEqual(minBw, 100)
        self.assertEqual(maxRl, 126000000)
    
    def test_IQBLK_IQBandwidth(self):
        iqBw = 20e6
        self.assertIsNone(IQBLK_SetIQBandwidth(iqBw))
        self.assertEqual(iqBw, IQBLK_GetIQBandwidth())
        self.assertRaises(ValueError, IQBLK_SetIQBandwidth, neg)
        self.assertRaises(ValueError, IQBLK_SetIQBandwidth, 100e6)
        self.assertRaises(TypeError, IQBLK_SetIQBandwidth, 'abc')
    
    def test_IQBLK_IQRecordLength(self):
        iqRl = 8192
        self.assertIsNone(IQBLK_SetIQRecordLength(iqRl))
        self.assertEqual(iqRl, IQBLK_GetIQRecordLength())
        self.assertRaises(ValueError, IQBLK_SetIQRecordLength, neg)
        self.assertRaises(ValueError, IQBLK_SetIQRecordLength, 200e6)
        self.assertRaises(TypeError, IQBLK_SetIQRecordLength, 'abc')

    def test_IQBLK_GetSampleRate(self):
        self.assertIsInstance(IQBLK_GetIQSampleRate(), float)
    
    def test_IQBLK_GetIQData(self):
        rl = 1000
        IQBLK_Configure() # Configure to defaults
        i, q = IQBLK_Acquire(IQBLK_GetIQDataDeinterleaved, rl, 10)
        self.assertEqual(len(i), rl)
        self.assertEqual(len(q), rl)
        
        iq = IQBLK_Acquire(IQBLK_GetIQData, rl, 10)
        self.assertEqual(len(iq), rl * 2)
        
        self.assertRaises(ValueError, IQBLK_Acquire, recLen=neg)
        self.assertRaises(ValueError, IQBLK_Acquire, recLen=200000000)
        self.assertRaises(TypeError, IQBLK_Acquire, recLen='abc')

    """IQSTREAM Command Testing"""
    
    def test_IQSTREAM_MinMaxIQBandwidth(self):
        minBandwidthHz = IQSTREAM_GetMinAcqBandwidth()
        maxBandwidthHz = IQSTREAM_GetMaxAcqBandwidth()
        self.assertEqual(minBandwidthHz, 9765.625)
        self.assertEqual(maxBandwidthHz, 40e6)
    
    def test_IQSTREAM_AcqBandwidth(self):
        bwHz_req = [40e6, 20e6, 10e6, 5e6, 2.5e6, 1.25e6, 625e3, 312.5e3,
                    156.25e3, 78125, 39062.5, 19531.25, 9765.625]
        srSps_req = [56e6, 28e6, 14e6, 7e6, 3.5e6, 1.75e6, 875e3,
                     437.5e3, 218.75e3, 109.375e3, 54687.5, 27343.75,
                     13671.875]
        baseSize = [65536, 65536, 65536, 65536, 65536, 32768, 16384, 8192,
                    4096, 2048, 1024, 512, 256, 128]
        for b, s, r in zip(bwHz_req, srSps_req, baseSize):
            self.assertIsNone(IQSTREAM_SetAcqBandwidth(b))
            bwHz_act, srSps = IQSTREAM_GetAcqParameters()
            self.assertEqual(bwHz_act, b)
            self.assertEqual(srSps, s)
            self.assertIsNone(IQSTREAM_SetIQDataBufferSize(r))
            self.assertEqual(IQSTREAM_GetIQDataBufferSize(), r)
        
        self.assertRaises(TypeError, IQSTREAM_SetAcqBandwidth, 'abc')
        self.assertRaises(TypeError, IQSTREAM_SetAcqBandwidth, [num])
        self.assertRaises(ValueError, IQSTREAM_SetAcqBandwidth, 41e6)
    
    def test_IQSTREAM_SetOutputConfiguration(self):
        dest = ['CLIENT', 'FILE_TIQ', 'FILE_SIQ', 'FILE_SIQ_SPLIT']
        dtype = ['SINGLE', 'INT32', 'INT16', 'SINGLE_SCALE_INT32']
        
        for d in dest:
            for t in dtype:
                if d is 'FILE_TIQ' and 'SINGLE' in t:
                    self.assertRaises(RSA_Error,
                                      IQSTREAM_SetOutputConfiguration, d, t)
                else:
                    self.assertIsNone(IQSTREAM_SetOutputConfiguration(d, t))
        
        self.assertRaises(TypeError, IQSTREAM_SetOutputConfiguration,
                          num, dtype[0])
        self.assertRaises(TypeError, IQSTREAM_SetOutputConfiguration,
                          dest[0], num)
        self.assertRaises(RSA_Error, IQSTREAM_SetOutputConfiguration, 'a', 'SINGLE')
        self.assertRaises(RSA_Error, IQSTREAM_SetOutputConfiguration, 'CLIENT', 'a')

    def test_IQSTREAM_SetDiskFilenameBase(self):
        path = '/tmp/rsa_api_unittest'
        if not isdir(path):
            mkdir(path)
        filename = 'iqstream_test'
        filenameBase = path + filename
        self.assertIsNone(IQSTREAM_SetDiskFilenameBase(filenameBase))
        
        self.assertRaises(TypeError, IQSTREAM_SetDiskFilenameBase, num)
        self.assertRaises(TypeError, IQSTREAM_SetDiskFilenameBase, b'abc')
        self.assertRaises(TypeError, IQSTREAM_SetDiskFilenameBase, [num])
    
    def test_IQSTREAM_SetDiskFilenameSuffix(self):
        suffixCtl = [0, -1, -2]
        for s in suffixCtl:
            self.assertIsNone(IQSTREAM_SetDiskFilenameSuffix(s))
        
        self.assertRaises(TypeError, IQSTREAM_SetDiskFilenameSuffix, 'abc')
        self.assertRaises(ValueError, IQSTREAM_SetDiskFilenameSuffix, neg)
    
    def test_IQSTREAM_SetDiskFileLength(self):
        length = 100
        self.assertIsNone(IQSTREAM_SetDiskFileLength(length))
        self.assertRaises(TypeError, IQSTREAM_SetDiskFileLength, 'abc')
        self.assertRaises(ValueError, IQSTREAM_SetDiskFileLength, neg)
    
    def test_IQSTREAM_Operation(self):
        IQSTREAM_SetAcqBandwidth(5e6)
        IQSTREAM_SetOutputConfiguration('CLIENT', 'INT16')
        IQSTREAM_GetAcqParameters()
        DEVICE_Run()
        
        self.assertIsNone(IQSTREAM_Start())
        self.assertTrue(IQSTREAM_GetEnable())
        
        self.assertIsNone(IQSTREAM_Stop())
        self.assertFalse(IQSTREAM_GetEnable())
        
        DEVICE_Stop()
    
    def test_IQSTREAM_ClearAcqStatus(self):
        self.assertIsNone(IQSTREAM_ClearAcqStatus())

    """TRIG Command Testing"""
    
    def test_TRIG_TriggerMode(self):
        mode = ["freeRun", "triggered"]
        for m in mode:
            self.assertIsNone(TRIG_SetTriggerMode(m))
            self.assertEqual(TRIG_GetTriggerMode(), m)
    
    def test_TRIG_TriggerSource(self):
        source = ["External", "IFPowerLevel"]
        for s in source:
            self.assertIsNone(TRIG_SetTriggerSource(s))
            self.assertEqual(TRIG_GetTriggerSource(), s)
    
    def test_TRIG_TriggerTransition(self):
        trans = ["LH", "HL", "Either"]
        for t in trans:
            self.assertIsNone(TRIG_SetTriggerTransition(t))
            self.assertEqual(TRIG_GetTriggerTransition(), t)
        self.assertRaises(TypeError, TRIG_SetTriggerTransition, 0)
    
    def test_TRIG_IFPowerTriggerLevel(self):
        trigLevel = -10
        self.assertIsNone(TRIG_SetIFPowerTriggerLevel(trigLevel))
        self.assertEqual(TRIG_GetIFPowerTriggerLevel(), trigLevel)
        self.assertRaises(TypeError, TRIG_SetIFPowerTriggerLevel, 'trigger')
        self.assertRaises(ValueError, TRIG_SetIFPowerTriggerLevel, 31)
        self.assertRaises(ValueError, TRIG_SetIFPowerTriggerLevel, -131)
    
    def test_TRIG_TriggerPositionPercent(self):
        self.assertRaises(ValueError, TRIG_SetTriggerPositionPercent, 0.5)
        self.assertRaises(ValueError, TRIG_SetTriggerPositionPercent, 100)
        self.assertRaises(TypeError, TRIG_SetTriggerPositionPercent, 'abc')
        
        pos = 20
        self.assertIsNone(TRIG_SetTriggerPositionPercent(pos))
        self.assertEqual(TRIG_GetTriggerPositionPercent(), pos)
    
    def test_TRIG_ForceTrigger(self):
        self.assertIsNone(TRIG_ForceTrigger())
    
    """REFTIME Command Testing"""
    
    def test_REFTIME_GetTimestampRate(self):
        self.assertEqual(REFTIME_GetTimestampRate(), 112000000)
    
    def test_REFTIME_TimeConversion(self):
        o_timeSec, o_timeNsec, o_timestamp = REFTIME_GetCurrentTime()
        test_timeSec, test_timeNsec = REFTIME_GetTimeFromTimestamp(
            o_timestamp)
        test_timestamp = REFTIME_GetTimestampFromTime(o_timeSec, o_timeNsec)
        REFTIME_SetReferenceTime(o_timeSec, o_timeNsec, o_timestamp)
        refTimeSec, refTimeNsec, refTimestamp = REFTIME_GetReferenceTime()
        
        self.assertEqual(o_timeSec, test_timeSec)
        self.assertEqual(o_timeNsec, test_timeNsec)
        self.assertEqual(o_timestamp, test_timestamp)
        self.assertEqual(o_timeSec, refTimeSec)
        self.assertEqual(o_timeNsec, refTimeNsec)
        self.assertEqual(o_timestamp, refTimestamp)

    def test_REFTIME_GetIntervalSinceRefTimeSet(self):
        self.assertIsInstance(REFTIME_GetIntervalSinceRefTimeSet(), float)

    def test_REFTIME_GetReferenceTimeSource(self):
        self.assertIsInstance(REFTIME_GetReferenceTimeSource(), str)
    
    """SPECTRUM Command Testing"""
    
    def test_SPECTRUM_Enable(self):
        enable = [False, True]
        for e in enable:
            self.assertIsNone(SPECTRUM_SetEnable(e))
            self.assertEqual(SPECTRUM_GetEnable(), e)
    
    def test_SPECTRUM_Settings(self):
        self.assertIsNone(SPECTRUM_SetDefault())
        
        span = 20e6
        rbw = 100e3
        enableVBW = True
        vbw = 50e3
        traceLength = 1601
        window = 'Hann'
        verticalUnit = 'dBm'
        self.assertIsNone(SPECTRUM_SetSettings(span, rbw, enableVBW, vbw,
                                                  traceLength, window,
                                                  verticalUnit))
        settings = SPECTRUM_GetSettings()
        self.assertIsInstance(settings, dict)
        self.assertEqual(len(settings), 13)
        self.assertEqual(settings['span'], span)
        self.assertEqual(settings['rbw'], rbw)
        self.assertEqual(settings['enableVBW'], enableVBW)
        self.assertEqual(settings['vbw'], vbw)
        self.assertEqual(settings['window'], window)
        self.assertEqual(settings['traceLength'], traceLength)
        self.assertEqual(settings['verticalUnit'], verticalUnit)
        
        self.assertRaises(TypeError, SPECTRUM_SetSettings, 'span', 'rbw',
                          'enableVBW', 'vbw', 'traceLength',
                          1, 0)
    
    def test_SPECTRUM_TraceType(self):
        trace = 'Trace2'
        enable = True
        detector = 'AverageVRMS'
        self.assertIsNone(SPECTRUM_SetTraceType(trace, enable, detector))
        o_enable, o_detector = SPECTRUM_GetTraceType(trace)
        self.assertEqual(enable, o_enable)
        self.assertEqual(detector, o_detector)
        
        self.assertRaises(RSA_Error, SPECTRUM_SetTraceType, trace='abc')
        self.assertRaises(TypeError, SPECTRUM_SetTraceType, trace=40e5)
        self.assertRaises(RSA_Error, SPECTRUM_SetTraceType,
                          detector='abc')
        self.assertRaises(TypeError, SPECTRUM_SetTraceType, detector=40e5)
    
    def test_SPECTRUM_GetLimits(self):
        limits = SPECTRUM_GetLimits()
        self.assertIsInstance(limits, dict)
        self.assertEqual(len(limits), 8)
        self.assertEqual(limits['maxSpan'], 6.2e9)
        self.assertEqual(limits['minSpan'], 1e3)
        self.assertEqual(limits['maxRBW'], 10e6)
        self.assertEqual(limits['minRBW'], 10)
        self.assertEqual(limits['maxVBW'], 10e6)
        self.assertEqual(limits['minVBW'], 1)
        self.assertEqual(limits['maxTraceLength'], 64001)
        self.assertEqual(limits['minTraceLength'], 801)
    
    def test_SPECTRUM_Acquire(self):
        SPECTRUM_SetEnable(True)
        span = 20e6
        rbw = 100e3
        enableVBW = True
        vbw = 50e3
        traceLength = 1601
        window = 'Hann'
        verticalUnit = 'dBm'
        SPECTRUM_SetSettings(span, rbw, enableVBW, vbw, traceLength, window,
                                verticalUnit)
        spectrum, outTracePoints = SPECTRUM_Acquire(trace='Trace1',
                                       tracePoints=traceLength)
        self.assertEqual(len(spectrum), traceLength)
        self.assertIsInstance(spectrum, np.ndarray)
        self.assertRaises(TypeError, SPECTRUM_Acquire, trace=1)
        
        traceInfo = SPECTRUM_GetTraceInfo()
        self.assertIsInstance(traceInfo, dict)
        self.assertEqual(len(traceInfo), 2)

if __name__ == '__main__':
    """There must be a connected RSA 306B in order to test."""
    DEVICE_Connect(0)
    if DEVICE_GetNomenclature() != 'RSA306B':
        raise Exception('Incorrect RSA model, please connect RSA306B')
    
    # Some values used in testing
    num = 400
    neg = -400
    unittest.main()
    
    # Test cleanup
    DEVICE_Stop()
    DEVICE_Disconnect()
