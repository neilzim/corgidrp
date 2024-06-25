# A file that holds the functions that transmogrify l2a data to l2b data 
import numpy as np
import corgidrp.data as data

def add_photon_noise(input_dataset):
    """
    Propagate the photon noise determined from the image signal to the error map.
    The image values must already be in units of photons 

    Args:
       input_dataset (corgidrp.data.Dataset): a dataset of Images with values in photons (L2a-level)
    
    Returns:
        corgidrp.data.Dataset: photon noise propagated to the image error extensions of the input dataset
    """
    # you should make a copy the dataset to start
    phot_noise_dataset = input_dataset.copy() # necessary at all?
    
    for i, frame in enumerate(phot_noise_dataset.frames):
        frame.add_error_term(np.sqrt(frame.data), "photnoise_error")
    
    new_all_err = np.array([frame.err for frame in phot_noise_dataset.frames])        
                
    history_msg = "photon noise propagated to error map"
    # update the output dataset
    phot_noise_dataset.update_after_processing_step(history_msg, new_all_err = new_all_err)
    
    return phot_noise_dataset


def dark_subtraction(input_dataset, dark_frame):
    """
    
    Perform dark current subtraction of a dataset using the corresponding dark frame

    Args:
        input_dataset (corgidrp.data.Dataset): a dataset of Images that need dark subtraction (L2a-level)
        dark_frame (corgidrp.data.Dark): a Dark frame to model the dark current

    Returns:
        corgidrp.data.Dataset: a dark subtracted version of the input dataset including error propagation
    """
    # you should make a copy the dataset to start
    darksub_dataset = input_dataset.copy()

    darksub_cube = darksub_dataset.all_data - dark_frame.data
    
    # propagate the error of the dark frame
    if hasattr(dark_frame, "err"):
        darksub_dataset.add_error_term(dark_frame.err[0], "dark_error")   
    else:
        raise Warning("no error attribute in the dark frame")
    
    #darksub_dataset.all_err = np.array([frame.err for frame in darksub_dataset.frames])
    history_msg = "Dark current subtracted using dark {0}".format(dark_frame.filename)

    # update the output dataset with this new dark subtracted data and update the history
    darksub_dataset.update_after_processing_step(history_msg, new_all_data=darksub_cube, header_entries = {"BUNIT":"photoelectrons"})

    return darksub_dataset

def frame_select(input_dataset, bpix_frac=1., overexp=False, tt_thres=None):
    """
    
    Selects the frames that we want to use for further processing.

    Args:
        input_dataset (corgidrp.data.Dataset): a dataset of Images (L2a-level)
        bpix_frac (float): greater than fraction of the image needs to be bad to discard. Default: 1.0 (not used)
        overexp (bool): if True, removes frames where the OVEREXP keyword is True. Default: False
        tt_thres (float): maximum allowed tip/tilt in image to be considered good. Default: None (not used) 

    Returns:
        corgidrp.data.Dataset: a version of the input dataset with only the frames we want to use
    """
    pruned_dataset = input_dataset.copy()
    select_flags = np.ones(len(input_dataset))

    for i, frame in enumerate(input_dataset.frames):
        if bpix_frac < 1:
            numbadpix = np.size(np.where(frame.dq > 0)[0])
            frame_badpix_frac = numbadpix / np.size(frame.dq)
            # if fraction of bad pixel over threshold, mark is as bad
            if frame_badpix_frac > bpix_frac:
                select_flags[i] = 0
        if overexp:
            if frame.ext_hdr['OVEREXP']:
                select_flags[i] = 0 
        if tt_thres is not None:
            if frame.ext_hdr['RESZ2RMS'] > tt_thres:
                select_flags[i] = 0
    
    good_frames = np.where(select_flags == 1)
    bad_frames = np.where(select_flags == 0)
    # check that we didn't remove all of the good frames
    if np.size(good_frames) == 0:
        raise ValueError("No good frames were selected. Unable to continue")

    pruned_frames = pruned_dataset.frames[good_frames]
    pruned_dataset = data.Dataset(pruned_frames)

    # history message of which frames were removed.
    history_msg = "Removed {0} frames:".format(np.size(bad_frames))
    for bad_frame in input_dataset.frames[bad_frames]:
        history_msg += " {0},".format(bad_frame.filename)
    history_msg = history_msg[:-1] # remove last comma or :

    pruned_dataset.update_after_processing_step(history_msg)

    return pruned_dataset

def convert_to_electrons(input_dataset, k_gain): 
    """
    
    Convert the data from ADU to electrons. 
    TODO: Establish the interaction with the CalDB for obtaining gain calibration 

    Args:
        input_dataset (corgidrp.data.Dataset): a dataset of Images (L2a-level)
        k_gain (corgidrp.data.KGain): KGain calibration file

    Returns:
        corgidrp.data.Dataset: a version of the input dataset with the data in electrons
    """
   # you should make a copy the dataset to start
    kgain_dataset = input_dataset.copy()
    kgain_cube = kgain_dataset.all_data
    kgain_error = kgain_dataset.all_err
    
    kgain = k_gain.value #extract from caldb
    kgain_cube *= kgain
    kgain_error *= kgain
    
    history_msg = "data converted to detected EM electrons by kgain {0}".format(str(kgain))

    # update the output dataset with this converted data and update the history
    kgain_dataset.update_after_processing_step(history_msg, new_all_data=kgain_cube, new_all_err=kgain_error, header_entries = {"BUNIT":"detected EM electrons", "KGAIN":kgain})
    return kgain_dataset

def em_gain_division(input_dataset):
    """
    
    Convert the data from detected EM electrons to detected electrons by dividing the commanded em_gain. 
    Update the change in units in the header [detected electrons].

    Args:
        input_dataset (corgidrp.data.Dataset): a dataset of Images (L2a-level)

    Returns:
        corgidrp.data.Dataset: a version of the input dataset with the data in units "detected electrons"
    """
    
    # you should make a copy the dataset to start
    emgain_dataset = input_dataset.copy()
    emgain_cube = emgain_dataset.all_data
    emgain_error = emgain_dataset.all_err
    
    unique = True
    emgain = emgain_dataset[0].ext_hdr["CMDGAIN"]
    for i in range(len(emgain_dataset)): 
        if emgain != emgain_dataset[i].ext_hdr["CMDGAIN"]:
            unique = False
            emgain = emgain_dataset[i].ext_hdr["CMDGAIN"] 
        emgain_cube[i] /= emgain
        emgain_error[i] /= emgain
    
    if unique:
        history_msg = "data divided by em_gain {0}".format(str(emgain))
    else:
        history_msg = "data divided by non-unique em_gain"

    # update the output dataset with this em_gain divided data and update the history
    emgain_dataset.update_after_processing_step(history_msg, new_all_data=emgain_cube, new_all_err=emgain_error, header_entries = {"BUNIT":"detected electrons"})

    return emgain_dataset

def cti_correction(input_dataset):
    """
    
    Apply the CTI correction to the dataset.
    TODO: Establish the interaction with the CalDB for obtaining CTI correction calibrations

    Args:
        input_dataset (corgidrp.data.Dataset): a dataset of Images (L2a-level)
        
    Returns:
        corgidrp.data.Dataset: a version of the input dataset with the CTI correction applied
    """

    return input_dataset.copy()

def flat_division(input_dataset, master_flat):
    """
    
    Divide the dataset by the master flat field. 

    Args:
        input_dataset (corgidrp.data.Dataset): a dataset of Images (L2a-level)
        master_flat (corgidrp.data.Flat): a master flat field to divide by

    Returns:
        corgidrp.data.Dataset: a version of the input dataset with the flat field divided out
    """

    return input_dataset.copy()

def correct_bad_pixels(input_dataset):
    """
    
    Compute bad pixel map and correct for bad pixels. 

    MMB Notes: 
        - We'll likely want to be able to accept an external bad pixel map, either 
        from the CalDB or input by a user. 
        - We may want to accept just a list of bad pixels from a user too, thus 
        saving them the trouble of actually making their own map. 
        - We may want flags to decide which pixels in the DQ we correct. We may 
        not want to correct everything in the DQ extension
        - Different bad pixels in the DQ may be corrected differently.


    Args:
        input_dataset (corgidrp.data.Dataset): a dataset of Images (L2a-level)

    Returns:
        corgidrp.data.Dataset: a version of the input dataset with bad pixels corrected
    """

    return input_dataset.copy()

