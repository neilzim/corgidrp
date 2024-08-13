import argparse
import os
import glob
import pytest
import numpy as np
import astropy.time as time
import astropy.io.fits as fits
import corgidrp
import corgidrp.data as data
import corgidrp.mocks as mocks
import corgidrp.walker as walker
import corgidrp.caldb as caldb
from corgidrp.calibrate_kgain import calibrate_kgain

thisfile_dir = os.path.dirname(__file__) # this file's folder

tvac_kgain = 8.7 #e/DN
tvac_readnoise = 133 #e

@pytest.mark.e2e
def test_l1_to_kgain(tvacdata_path, e2eoutput_path):
    # figure out paths, assuming everything is located in the same relative location
    l1_datadir = os.path.join(tvacdata_path, "TV-20_EXCAM_noise_characterization", "kgain")
    print(l1_datadir)
    l1_datadir_nonlin = os.path.join(tvacdata_path, "TV-20_EXCAM_noise_characterization", "nonlin")
    nonlin_path = os.path.join(tvacdata_path, "TV-20_EXCAM_noise_characterization", "results", "nonlin_table_240322.txt")
    kgain_result = os.path.join(tvacdata_path, "TV-20_EXCAM_noise_characterization", "results", "kgain_read_noise.txt")

    # make output directory if needed
    kgain_outputdir = os.path.join(e2eoutput_path, "l1_to_kgain_output")
    if not os.path.exists(kgain_outputdir):
        os.mkdir(kgain_outputdir)

    # define the raw science data to process

    l1_data_filelist_same_exp = [os.path.join(l1_datadir, "CGI_EXCAM_L1_00000{0}.fits".format(i)) for i in np.arange(51841,51870)]#[51841, 51870]] # just grab some files of it
    print(l1_data_filelist_same_exp)
    l1_data_filelist_range_exp = [os.path.join(l1_datadir, "CGI_EXCAM_L1_00000{0}.fits".format(i)) for i in np.arange(51731, 51760)]#[51731, 51840]]
    print(l1_data_filelist_range_exp)
    mock_cal_filelist = [os.path.join(l1_datadir_nonlin, "CGI_EXCAM_L1_00000{0}.fits".format(i)) for i in [51825, 55165]] # grab some real data to mock the calibration 
    
    ###### Setup necessary calibration files
    # Create necessary calibration files
    # we are going to make a new nonlinear calibration file using
    # a combination of the II&T nonlinearity file and the mock headers from
    # our unit test version of the NonLinearityCalibration
    nonlin_dat = np.genfromtxt(nonlin_path, delimiter=",")
    pri_hdr, ext_hdr = mocks.create_default_headers()
    ext_hdr["DRPCTIME"] = time.Time.now().isot
    ext_hdr['DRPVERSN'] =  corgidrp.__version__
    mock_input_dataset = data.Dataset(mock_cal_filelist)
    nonlinear_cal = data.NonLinearityCalibration(nonlin_dat,
                                                 pri_hdr=pri_hdr,
                                                 ext_hdr=ext_hdr,
                                                 input_dataset=mock_input_dataset)
    nonlinear_cal.save(filedir=kgain_outputdir, filename="mock_nonlinearcal.fits" )

    # add calibration file to caldb
    this_caldb = caldb.CalDB()
    this_caldb.create_entry(nonlinear_cal)

    ####### Run the walker on some test_data

    for file in l1_data_filelist_same_exp:
        l1_data_filelist_range_exp.append(file)
    print(l1_data_filelist_range_exp)
    walker.walk_corgidrp(l1_data_filelist_range_exp, "", kgain_outputdir, template="l1_to_kgain.json")
    kgain_files = glob.glob(os.path.join(kgain_outputdir, "CGI*.fits"))
    kgain_files.sort()
    print (kgain_files)
    dataset_kgain = data.Dataset(kgain_files)
    
    # clean up by removing entry
    this_caldb.remove_entry(nonlinear_cal)

    kgain = calibrate_kgain(dataset_kgain, 
                    n_cal=10, n_mean=30, min_val=800, max_val=3000, binwidth=68,
                    make_plot=True,plot_outdir='figures', show_plot=True, 
                    logspace_start=-1, logspace_stop=4, logspace_num=200, 
                    verbose=False, detector_regions=None)
    
    ##### Check against TVAC kgain, readnoise
    new_kgain = kgain.value
    new_readnoise = kgain.exthdr["RN"]
        
    diff_kgain = new_kgain - tvac_kgain
    diff_readnoise = new_readnoise - tvac_readnoise
    print ("difference to TVAC kgain:", diff_kgain)
    print ("difference to TVAC readnoise:", diff_readnoise)
    print ("error of kgain:", kgain.error)
    print ("error of  readnoise:", kgain.exthdr["RN_ERR"])

    assert np.abs(diff_kgain) < 1e-2
    assert np.abs(diff_readnoise) < 1

    # # plotting script for debugging
    # import matplotlib.pylab as plt
    # plot the PTC
    ptc = kgain.ptc
    print(ptc)
    
if __name__ == "__main__":
    # Use arguments to run the test. Users can then write their own scripts
    # that call this script with the correct arguments and they do not need
    # to edit the file. The arguments use the variables in this file as their
    # defaults allowing the use to edit the file if that is their preferred
    # workflow.
    tvacdata_dir = "/home/schreiber/DataCopy/corgi/CGI_TVAC_Data/"
    outputdir = thisfile_dir

    ap = argparse.ArgumentParser(description="run the l1->kgain end-to-end test")
    ap.add_argument("-tvac", "--tvacdata_dir", default=tvacdata_dir,
                    help="Path to CGI_TVAC_Data Folder [%(default)s]")
    ap.add_argument("-o", "--outputdir", default=outputdir,
                    help="directory to write results to [%(default)s]")
    args = ap.parse_args()
    tvacdata_dir = args.tvacdata_dir
    outputdir = args.outputdir
    test_l1_to_kgain(tvacdata_dir, outputdir)
