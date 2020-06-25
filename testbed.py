import numpy as np
import scipy.optimize as opt
import scipy.special as sf
import matplotlib.pyplot as plt
from matplotlib import rc as mpl_rc
from matplotlib.ticker import StrMethodFormatter
from time import sleep, strftime
# The next import also loads the RSA driver and device
# It may be better to load the driver/device in this file instead
from RSA_API import *

""" PLOT FORMATTING STUFF """
mpl_rc('xtick', direction='in', top=True)
mpl_rc('ytick', direction='in', right=True)
mpl_rc('xtick.minor', visible=True)
mpl_rc('ytick.minor', visible=True)

""" DATA COLLECTION METHODS """

# Collect an IQ Block of data
def iqblk_collect(recordLength=1024):
    # Acquire and return IQ Block data
    # !! Configure device BEFORE calling this method
    # Input: Record length [num. of samples]
    # Returns numpy array of complex data: I+Qj

    # Record length must be an integer
    recordLength = int(recordLength)
    ready = c_bool(False)
    iqArray = c_float * recordLength
    iData = iqArray()
    qData = iqArray()
    outLength = c_int(0)

    # Begin data acquisition
    rsa.DEVICE_Run()
    rsa.IQBLK_AcquireIQData()

    # Wait for device to be ready to send data
    while not ready.value:
        # Currenty uses 100ms timeout
        rsa.IQBLK_WaitForIQDataReady(c_int(100), byref(ready))

    # Retrieve data
    rsa.IQBLK_GetIQDataDeinterleaved(byref(iData), byref(qData),
        byref(outLength), c_int(recordLength))

    # Stop device before exiting
    rsa.DEVICE_Stop()

    return np.array(iData) + 1j * np.array(qData)

# Plot an IQ data block
def iqblk_plot(time, IQ, show=True, save=False, path=".", filename="IQ_vs_Time_Plot"):
    # Plots IQ data
    # Input: Complex numpy array of (I + Qj) values

    fig = plt.figure()
    ax1 = plt.subplot(211)
    ax1.set_title('I and Q vs Time')
    ax1.plot(time, np.real(IQ), color='r')
    ax1.set_ylabel('I')
    ax1.set_xlim(0, time[-1])
    ax1.grid(which='major', axis='both', alpha=0.75)
    ax1.grid(which='minor', axis='both', alpha=0.25)
    ax2 = plt.subplot(212)
    ax2.plot(time, np.imag(IQ), color='c')
    ax2.set_ylabel('Q')
    ax2.set_xlabel('Time (s)')
    ax2.set_xlim(0, time[-1])
    ax2.grid(which='major', axis='both', alpha=0.75)
    ax2.grid(which='minor', axis='both', alpha=0.25)
    plt.tight_layout()

    # Save figure to file
    if save:
        fname = path + strftime("/%m%d%Y-%H%M%S_") + filename + '.png'
        fig.savefig(fname, dpi=300, bbox_inches='tight')

    if show:
        plt.show()

# Master function for IQ collection testing
def iqblk_master(cf=1e9, refLevel=0, iqBw=40e6, recordLength=1024, save=False,
    filename="IQ_Data", path='.', plot=False, savefig=False, figname="IQ_vs_Time_Plot"):
    # Inputs:
    # cf: Center frequency [Hz]
    # refLevel: Reference level [dBm]
    # iqBw: IQ Bandwidth [Hz] (determines sampling rate)
    # recordLength: IQ Block length [samples]
    # save: Boolean, determines if data is saved to file
    # filename: appended to timestap if saving file
    # path: prefixed to file name, use to set a path/folder
    # plot: Boolean, determines if data is plotted when 

    connect()

    # Set parameters
    set_centerFreq(cf)
    set_refLevel(refLevel)
    set_iqBandwidth(iqBw)
    set_iqRecordLength(recordLength)

    # Sample rate is determined by BW set above
    iqSampleRate = get_iqSampleRate()

    # Acquire data
    IQ = iqblk_collect(recordLength)

    disconnect()

    # Plotting
    if plot:
        # Create array of time data for plotting IQ vs time
        time = np.linspace(0, recordLength / iqSampleRate, recordLength)
        iqblk_plot(time, IQ, save=savefig, path=path, filename=figname)

    # Save data to file
    if save:
        headerInfo = ("IQ DATA FILE\nCF: " + str(cf) + " Hz, Ref. Level: "
            + str(refLevel) + " dBm, BW: " + str(iqBw) + " Hz, Rec. Length: " 
            + str(recordLength) + " samples, SR: " + str(iqSampleRate))
        fname = path + strftime("/%m%d%Y-%H%M%S_") + filename + '.txt'
        np.savetxt(fname, IQ, header=headerInfo)
    
    return IQ

# Investigation of BW vs SR
def char_sampleRate():
    connect()

    minBandwidth = get_minIqBandwidth()
    maxBandwidth = get_maxIqBandwidth()
    bwRange = np.linspace(minBandwidth, maxBandwidth, 2000)
    srRange = np.zeros_like(bwRange)

    for (i, bw) in enumerate(bwRange):
        set_iqBandwidth(bw)
        iqSr = get_iqSampleRate()
        srRange[i] = iqSr

    disconnect()

    fig = plt.figure()
    ax = fig.add_subplot(111)
    ax.plot(bwRange, srRange, 'k.')
    ax.set_xlabel("Bandwidth [Hz]")
    ax.set_ylabel("Sample Rate, [samples/s]")
    ax.set_title("IQ Sample Rate vs. Manually Set IQ Bandwidth")
    ax.grid(True, which='major', axis='both', alpha=0.75)
    ax.grid(True, which='minor', axis='both', alpha=0.25)
    plt.show()

# Take IQ Data FFT + Calculate M4S
def iq_fft(iqData):
    # iqData: IQ data array

    (numFFTs, recLength) = np.shape(iqData)

    # Take FFT and normalize
    complex_fft = np.fft.fftshift(np.fft.fft(iqData))

    # Convert to psuedo-power
    complex_fft = np.square(np.abs(complex_fft))
    
    # Create the detector result
    m4s_detected = np.zeros((5, recLength), dtype=np.float32)

    # Run detector
    m4s_detected[0] = np.min(complex_fft, axis=0)
    m4s_detected[1] = np.max(complex_fft, axis=0)
    m4s_detected[2] = np.mean(complex_fft, axis=0)
    m4s_detected[3] = np.median(complex_fft, axis=0)
    for i in range(recLength):
        m4s_detected[4][i] = complex_fft[np.random.randint(0, numFFTs)][i]

    # Convert to power
    impedance_factor = -10*np.log10(50)
    m4s_detected = 10*np.log10(m4s_detected) + impedance_factor + 30
    m4s_detected -= 3 # Account for double sided FFT

    # Normalize FFT
    fft_normalization_factor = -20*np.log10(len(m4s_detected[0]))
    m4s_detected += fft_normalization_factor

    return m4s_detected

# Generate frequency axis points for an FFT
def generate_spectrum(f0, sr, n):
    # Taken from scos_algorithm_test.lib.utils
    freqs = np.arange(n, dtype=float)
    freqs *= sr/len(freqs)
    freqs += f0 - (sr/2)
    return freqs

# WiFi Spectrum testing FFT Plotter
def fft_plot(freqData, fftData, title):
    fig = plt.figure()
    ax = fig.add_subplot(111)
    ax.plot(freqData, fftData, color='r')
    ax.set_title(title)
    ax.set_ylabel('Power [dBm]')
    ax.set_xlabel('Frequency [Hz]')
    ax.set_xlim(freqData[0], freqData[-1])
    ax.grid(which='major', axis='both', alpha=0.75)
    ax.grid(which='minor', axis='both', alpha=0.25)
    plt.show()

# Master function for Wifi spectrum testing
def wifi_fft(cf=2.437e9, refLevel=-40, iqBw=40e6, recordLength=1024):
    # WIFI CHANNELS
    # 1: 2412 MHz
    # 6: 2437 MHz
    # 11: 2462 MHz

    numFFTs = 100
    iqArray = np.zeros((numFFTs, recordLength), dtype=complex)

    connect()

    print("Connected.\nTaking {} sets of IQ data...\n".format(numFFTs))

    set_centerFreq(cf)
    set_refLevel(refLevel)
    set_iqBandwidth(iqBw)
    set_iqRecordLength(recordLength)
    iqSampleRate = get_iqSampleRate()

    # Acquire Data:
    # Each row will be its own IQ data, each column its own data point
    for (num, vals) in enumerate(iqArray):
        iqArray[num] = iqblk_collect(recordLength)

    disconnect()

    print("Center Frequency: {} Hz\n".format(cf),
        "Reference Level: {} dBm\n".format(refLevel),
        "Bandwidth: {} Hz\n".format(iqBw),
        "Record Length: {} samples\n".format(recordLength),
        "Sample Rate: {} samples/sec\n".format(iqSampleRate))

    print("Constructing Mean FFT...")

    m4s_wifi = iq_fft(iqArray)
    freqPlotData = generate_spectrum(cf, iqSampleRate, recordLength)
    calcBw = freqPlotData[-1] - freqPlotData[0]
    print("Minimum Frequency: {}\n".format(freqPlotData[0]),
        "Maximum Frequency: {}\n".format(freqPlotData[-1]))
    print("Calculated BW: {}\n".format(calcBw))
    print("Full BW/Set BW: {}".format(calcBw/iqBw))
    fft_plot(freqPlotData, m4s_wifi[2], title="Mean FFT")

# Sample Rate Comparison Testing
def sr_test_plot(freqArr, meanFFTArr):
    fig = plt.figure()
    ax = fig.add_subplot(111)
    ax.set_title("Mean FFTs for Various IQ Bandwidths and Sample Rates")
    ax.set_xlabel("Frequency [Hz]")
    ax.set_ylabel("Power [dBm]")
    ax.set_xlim(freqArr[-1, 0], freqArr[-1, -1])
    ax.grid(which="major", axis="both", alpha=0.75)
    ax.grid(which="minor", axis="both", alpha=0.25)
    for (i, FFT) in enumerate(meanFFTArr):
        if i == 0:
            ax.plot(freqArr[i, :], FFT, color='k', label="BW: {:.2e}, SR: {:.2e}".format(bwArray[i], srArray[i]))
        if i == 1:
            ax.plot(freqArr[i, :], FFT, color='c', label="BW: {:.2e}, SR: {:.2e}".format(bwArray[i], srArray[i]))
        if i == 2:
            ax.plot(freqArr[i, :], FFT, color='r', label="BW: {:.2e}, SR: {:.2e}".format(bwArray[i], srArray[i]))
    ax.legend(loc='best')
    plt.show()

# Master function for FFT SR investigating
def sr_test_fft(cf=2.437e9, refLevel=-60, recordLength=1024):
    #bwArray = np.array([342, 684, 1368, 2735, 5469, 10938, 21876,
    #    43760, 87600, 176000, 360000, 701000, 1.5e6, 2.9e6, 5.7e6, 1.13e7, 2.25e7])
    #bwArray = np.array([1.13e7, 1.63e7, 2.13e7])
    bwArray = np.array([5.7e6, 1.13e7, 2.25e7])
    srArray = np.zeros_like(bwArray)

    numFFTs = 1000
    meanFFTArr = np.zeros((len(bwArray), recordLength))
    freqArr = np.zeros_like(meanFFTArr)
    #iqArray = np.zeros((numFFTs, recordLength), dtype=complex)

    connect()

    set_centerFreq(cf)
    set_refLevel(refLevel)

    for (i, bw) in enumerate(bwArray):
        set_iqBandwidth(bw)
        set_iqRecordLength(recordLength)
        srArray[i] = get_iqSampleRate()
        iqArray = np.zeros((numFFTs, recordLength), dtype=complex)
        for (num, vals) in enumerate(iqArray):
            iqArray[num] = iqblk_collect(recordLength)
        m4s_temp = iq_fft(iqArray)
        meanFFTArr[i] = m4s_temp[2]
        freqArr[i] = generate_spectrum(cf, srArray[i], recordLength)

    disconnect()

    sr_test_plot(freqArr, meanFFTArr)
    
# Master function for gain characterization
def gain_char(minRL, maxRL, numRLs, which="figure", hist=False):
    # "which" parameter chooses either "figure" or "power" for what is plotted
    # "figure" = noise figure, "power" = mean noise power
    # Or pass "none" to not create the plot (useful for making histograms only)

    if which is not "figure" and not "power" and not "none":
        print("Choose either figure, power, or none for the which parameter")
        return None

    # Data collection settings
    numFFTs = 1000
    cf = 3.6e9
    iqBw = 40e6
    recordLength = 1024

    # Create necessary variables
    compRecLen = numFFTs*recordLength
    refLev = np.linspace(minRL, maxRL, numRLs)
    avgNoisePwr = np.zeros_like(refLev)
    meanFFTArr = np.zeros((len(refLev), recordLength))
    iqArr = np.zeros((len(refLev), compRecLen), dtype=complex)
    freqArr = np.zeros_like(meanFFTArr)
    thermalNoise = theoryNoise(iqBw)

    connect()

    # Configure device
    set_centerFreq(cf)
    set_iqBandwidth(iqBw)
    set_iqRecordLength(compRecLen)
    sampRate = get_iqSampleRate()

    # Collect data
    for (i, RL) in enumerate(refLev):
        set_refLevel(RL)
        iqArray = np.zeros(compRecLen, dtype=complex)
        iqArray = iqblk_collect(compRecLen)
        iqSlice = np.zeros((numFFTs, recordLength), dtype=complex)
        for j in range(numFFTs):
            iqSlice[j] = iqArray[j*recordLength:(j+1)*recordLength]
        m4s_temp = iq_fft(iqSlice)
        meanFFTArr[i] = m4s_temp[2]
        freqArr[i] = generate_spectrum(cf, sampRate, recordLength)
        iqArr[i] = iqArray

    disconnect()

    if which is not "none":
        # Truncate freq domain data to the set bandwidth (remove tails)
        lowBound = findNearest(freqArr, cf - iqBw/2)
        highBound = findNearest(freqArr, cf + iqBw/2)
        newMeanFFTArr = np.zeros((len(refLev), highBound + 1 - lowBound))
        newFreqArr = np.zeros_like(newMeanFFTArr)
        for (i, arr) in enumerate(freqArr):
            newFreqArr[i] = arr[lowBound:highBound + 1]
        for (i, arr) in enumerate(meanFFTArr):
            newMeanFFTArr[i] = arr[lowBound:highBound + 1]

        # Calculate mean noise powers
        for (i, FFT) in enumerate(newMeanFFTArr):
            avgNoisePwr[i] = np.mean(FFT)

        # Plot desired noise quantity vs ref level
        noise_plot(refLev, avgNoisePwr, thermalNoise, which=which)

    # Plot IQ histograms
    if hist:
        gainChar_hist(iqArr, refLev)

def noise_plot(refLev, avgNoisePwr, thermalNoise, which="figure"):
    # Plots and fits noise vs. ref level data. Use for either noise figure or 
    # mean noise power vs. ref level, specified by "which" parameter

    # Handle cases
    if which == "figure":
        ydata = avgNoisePwr/thermalNoise
        quantity = "Noise Figure" # used for title and labels
        unit = "" # dimensionless
        p0 = np.array([-30, -110/thermalNoise, 0, 1]) # param guess for fit
        sigma_y = np.ones_like(ydata)/100 # 1/100 fractional error
        absErr = False
    elif which == "power":
        ydata = avgNoisePwr
        quantity = "Mean Noise Power"
        unit = " [dBm]" # appended to quantity for axis label
        p0 = np.array([-30, -110, 0, 1])
        sigma_y = np.ones_like(ydata)*1.5 # 1.5 dBm absolute error
        absErr = True
    else:
        print("Please enter either figure or power for the which parameter")
        return None

    # Model function for fitter
    def noise_model(x, x0, y0, k1, k2):
        return np.piecewise(x, [x < x0, x >= x0], [lambda x:k1*x + y0-k1*x0,
            lambda x:k2*x + y0-k2*x0])

    # Curve fitting + fit statistics
    (p, C) = opt.curve_fit(noise_model, refLev, ydata, sigma=sigma_y, absolute_sigma=absErr)
    sigp = np.sqrt(np.diag(C))
    chisq = np.sum(((ydata - noise_model(refLev, *p)) ** 2)/(sigma_y ** 2))
    dof = len(ydata) - len(p) # deg of freedom
    rChiSq = chisq/dof # Reduced Chisq
    Q = sf.gammaincc(0.5*dof, 0.5*chisq) # Goodness of fit

    # Print fit statistics
    print("Fit Statistics:\n"
        + "x0 = {:.3f} +/- {:.3f} dBm\n".format(p[0], sigp[0])
        + "y0 = {:.3f} +/- {:.3f}{}\n".format(p[1], sigp[1], unit)
        + "m1 = {:.3f} +/- {:.3f} \n".format(p[2], sigp[2])
        + "m2 = {:.3f} +/- {:.3f} \n".format(p[3], sigp[3])
        + "Chi Squared = {:.3f}\n".format(chisq)
        + "Reduced ChiSq = {:.3f}\n".format(rChiSq)
        + "Degress of Freedom = {}\n".format(dof)
        + "Goodness of Fit = {:.3f}\n".format(Q)
    )

    # Plotting
    refLevFine = np.linspace(refLev[0], refLev[-1], 1000) # For fit plot

    fig = plt.figure()
    ax = fig.add_subplot(111)
    ax.set_xlabel("Reference Level [dBm]")
    ax.set_ylabel(quantity + unit)
    ax.set_title("Tek RSA306b " + quantity + " vs. Reference Level")
    ax.grid(which="major", axis="both", alpha=0.75)
    ax.grid(which="minor", axis="both", alpha=0.4)
    ax.plot(refLev, ydata, 'k.', label=(quantity + " Data"))
    ax.plot(refLevFine, noise_model(refLevFine, *p), 'r--', label=
        "Curve Fit, ChiSq = {:.3f}".format(chisq))
    ax.legend()
    plt.show()

def gainChar_hist(iqData, refLevels, numBins=30):
    # Make histograms for sets of IQ samples
    # taken with various reference levels

    fig, ax = plt.subplots(len(refLevels), 3)
    ytick_fmt = StrMethodFormatter(('{x:,g}'))
    xtick_fmt = StrMethodFormatter(('{x:.3f}'))

    for (i, RL) in enumerate(refLevels):
        iData = np.real(iqData[i]) # V
        qData = np.imag(iqData[i]) # V
        pwrData = (np.abs(iqData[i])**2)/50 # W

        # I histogram
        ax[i][0].grid(which="major", axis="y", alpha=0.75)
        ax[i][0].grid(which="minor", axis="y", alpha=0.25)
        ax[i][0].hist(iData*1e3, numBins, label="Ref. Level = {} dBm".format(RL))
        ax[i][0].set_ylabel("Number")
        ax[i][0].yaxis.set_major_formatter(ytick_fmt)
        ax[i][0].xaxis.set_major_formatter(xtick_fmt)
        ax[i][0].legend()
        # Q histogram
        ax[i][1].grid(which="major", axis="y", alpha=0.75)
        ax[i][1].grid(which="minor", axis="y", alpha=0.25)
        ax[i][1].hist(qData*1e3, numBins, label="Ref. Level = {} dBm".format(RL))
        ax[i][1].yaxis.set_major_formatter(ytick_fmt)
        ax[i][1].xaxis.set_major_formatter(xtick_fmt)
        ax[i][1].legend()
        # Power histogram
        ax[i][2].grid(which="major", axis="y", alpha=0.75)
        ax[i][2].grid(which="minor", axis="y", alpha=0.25)
        ax[i][2].hist(pwrData*1e3, numBins, label="Ref. Level = {} dBm".format(RL))
        ax[i][2].yaxis.set_major_formatter(ytick_fmt)
        ax[i][2].xaxis.set_major_formatter(xtick_fmt)
        ax[i][2].legend()

    # Axis Labels
    ax[0][0].set_title("Histogram of I Data")
    ax[0][1].set_title("Histogram of Q Data")
    ax[0][2].set_title("Histogram of Power Data")
    ax[-1][0].set_xlabel("I (mV)")
    ax[-1][1].set_xlabel("Q (mV)")
    ax[-1][2].set_xlabel("Power (mW)")

    plt.gcf().subplots_adjust(bottom=0.15)
    plt.show()

def findNearest(arr, val):
    # Return index of array element nearest to value
    idx = np.abs(arr - val).argmin()
    return idx

def theoryNoise(bw, T=294.261):
    # Calculates thermal noise power
    # T: temp, kelvin
    # bw: bandwidth, Hz
    # Returns noise power in dBm
    k = 1.380649e-23 # J/K
    P_dBm = 10*np.log10(k*T*bw)
    return P_dBm

""" RUN STUFF """
#iqblk_master(1e9, 0, 40e6, 1024, plot=True, savefig=False)
#char_sampleRate()
#wifi_fft(iqBw=2.25e7)
#sr_test_fft(cf=4000e6)
gain_char(-130, 30, 50, which="figure", hist=False)