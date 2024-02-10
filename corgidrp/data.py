import os
import numpy as np
import numpy.ma as ma
import corgidrp
import astropy.io.fits as fits
import astropy.time as time

class Dataset():
    """
    A sequence of data of the same kind. Can be indexed and looped over

    Args:
        frames_or_filepaths (list): list of either filepaths or data objects (e.g., Image class)

    Attributes:
        all_data (np.array): an array with all the data combined together. First dimension is always number of images
        frames (list): list of data objects (probably corgidrp.data.Image)
    """
    def __init__(self, frames_or_filepaths):
        """
        Args:
            frames_or_filepaths (list): list of either filepaths or data objects (e.g., Image class)
        """
        if len(frames_or_filepaths) == 0:
            raise ValueError("Empty list passed in")

        if isinstance(frames_or_filepaths[0], str):
            # list of filepaths
            # TODO: do some auto detection of the filetype, but for now assume it is an image file
            self.frames = []
            for filepath in frames_or_filepaths:
                self.frames.append(Image(filepath))
        else:
            # list of frames
            self.frames = frames_or_filepaths

        # turn lists into np.array for indexing behavior
        if isinstance(self.frames, list):
            self.frames = np.array(self.frames) # list of objects

        # create 3-D cube of all the data
        self.all_data = np.array([frame.data for frame in self.frames])
        self.all_err = np.array([frame.err for frame in self.frames])
        self.all_dq = np.array([frame.dq for frame in self.frames])
        # do a clever thing to point all the individual frames to the data in this cube
        # this way editing a single frame will also edit the entire datacube
        for i, frame in enumerate(self.frames):
            frame.data = self.all_data[i]
            frame.err = self.all_err[i]
            frame.dq = self.all_dq[i]

    def __iter__(self):
        return self.frames.__iter__()

    def __getitem__(self, indices):
        if isinstance(indices, int):
            # return a single element of the data
            return self.frames[indices]
        else:
            # return a subset of the dataset
            return Dataset(self.frames[indices])

    def __len__(self):
        return len(self.frames)

    def save(self, filedir, filenames=None):
        """
        Save each file of data in this dataset into directory

        Args:
            filedir (str): directory to save the files
            filenames (list): a list of output filenames for each file

        """
        # if filenames are not passed, use the default ones
        if filenames is None:
            filenames = []
            for frame in self.frames:
                filename = frame.filename
                filenames.append(frame.filename)

        for filename, frame in zip(filenames, self.frames):
            frame.save(filename=filename, filedir=filedir)

    def update_after_processing_step(self, history_entry, new_all_data=None, new_all_err = None, new_all_dq = None):
        """
        Updates the dataset after going through a processing step

        Args:
            history_entry (str): a description of what processing was done. Mention reference files used.
            new_all_data (np.array): (optional) Array of new data. Needs to be the same shape as `all_data`
            new_all_err (np.array): (optional) Array of new err. Needs to be the same shape as `all_err`
            new_all_dq (np.array): (optional) Array of new dq. Needs to be the same shape as `all_dq`
        """
        # update data if necessary
        if new_all_data is not None:
            if new_all_data.shape != self.all_data.shape:
                raise ValueError("The shape of new_all_data is {0}, whereas we are expecting {1}".format(new_all_data.shape, self.all_data.shape))
            self.all_data[:] = new_all_data # specific operation overwrites the existing data rather than changing pointers
        if new_all_err is not None:
            if new_all_err.shape != self.all_err.shape:
                raise ValueError("The shape of new_all_err is {0}, whereas we are expecting {1}".format(new_all_err.shape, self.all_err.shape))
            self.all_err[:] = new_all_err # specific operation overwrites the existing data rather than changing pointers
        if new_all_dq is not None:
            if new_all_dq.shape != self.all_dq.shape:
                raise ValueError("The shape of new_all_dq is {0}, whereas we are expecting {1}".format(new_all_dq.shape, self.all_dq.shape))
            self.all_dq[:] = new_all_dq # specific operation overwrites the existing data rather than changing pointers

        # update history
        for img in self.frames:
            img.ext_hdr['HISTORY'] = history_entry


    def copy(self, copy_data=True):
        """
        Make a copy of this dataset, including all data and headers.
        Data copying can be turned off if you only want to modify the headers
        Headers should always be copied as we should modify them any time we make new edits to the data

        Args:
            copy_data (bool): (optional) whether the data should be copied. Default is True

        Returns:
            corgidrp.data.Dataset: a copy of this dataset
        """
        # there's a smarter way to manage memory, but to keep the API simple, we will avoid it for now
        new_frames = [frame.copy(copy_data=copy_data) for frame in self.frames]
        new_dataset = Dataset(new_frames)

        return new_dataset

class Image():
    """
    Base class for 2-D image data. Data can be created by passing in the data/header explicitly, or
    by passing in a filepath to load a FITS file from disk

    Args:
        data_or_filepath (str or np.array): either the filepath to the FITS file to read in OR the 2D image data
        pri_hdr (astropy.io.fits.Header): the primary header (required only if raw 2D data is passed in)
        ext_hdr (astropy.io.fits.Header): the image extension header (required only if raw 2D data is passed in)
        err (np.array): 2-D uncertainty data
        dq (np.array): 2-D data quality, 0: good, 1: bad

    Attributes:
        data (np.array): 2-D data for this Image
        err (np.array): 2-D uncertainty
        dq (np.array): 2-D data quality
        pri_hdr (astropy.io.fits.Header): primary header
        ext_hdr (astropy.io.fits.Header): ext_hdr. Generally this header will be edited/added to
        filename (str): the filename corresponding to this Image
        filedir (str): the file directory on disk where this image is to be/already saved.
        filepath (str): full path to the file on disk (if it exists)
    """
    def __init__(self, data_or_filepath, pri_hdr=None, ext_hdr=None, err = None, dq = None):
        if isinstance(data_or_filepath, str):
            # a filepath is passed in
            with fits.open(data_or_filepath) as hdulist:
                self.pri_hdr = hdulist[0].header
                # image data is in FITS extension
                self.ext_hdr = hdulist[1].header
                self.data = hdulist[1].data

                # we assume that if the err and dq array is given as parameter they supersede eventual err and dq extensions
                if err is not None:
                    if np.shape(self.data) != np.shape(err):
                        raise ValueError("The shape of err is {0} while we are expecting shape {1}".format(err.shape, self.data.shape))
                    self.err = err
                # we assume that the ERR extension is index 2 of hdulist
                elif len(hdulist)>2:
                    self.err = hdulist[2].data
                else:
                    self.err = np.zeros(self.data.shape)

                if dq is not None:
                    if np.shape(self.data) != np.shape(dq):
                        raise ValueError("The shape of dq is {0} while we are expecting shape {1}".format(dq.shape, self.data.shape))
                    self.dq = dq
                # we assume that the DQ extension is index 3 of hdulist
                elif len(hdulist)>3:
                    self.dq = hdulist[3].data
                else:
                    self.dq = np.zeros(self.data.shape, dtype = np.uint16)


            # parse the filepath to store the filedir and filename
            filepath_args = data_or_filepath.split(os.path.sep)
            if len(filepath_args) == 1:
                # no directory info in filepath, so current working directory
                self.filedir = "."
                self.filename = filepath_args[0]
            else:
                self.filename = filepath_args[-1]
                self.filedir = os.path.sep.join(filepath_args[:-1])

        else:
            # data has been passed in directly
            # creation of a new file in DRP eyes
            if pri_hdr is None or ext_hdr is None:
                raise ValueError("Missing primary and/or extension headers, because you passed in raw data")
            self.pri_hdr = pri_hdr
            self.ext_hdr = ext_hdr
            self.data = data_or_filepath
            self.filedir = "."
            self.filename = ""
            if err is not None:
                if np.shape(self.data) != np.shape(err):
                    raise ValueError("The shape of err is {0} while we are expecting shape {1}".format(err.shape, self.data.shape))
                self.err = err
            else:
                self.err = np.zeros(self.data.shape)
            if dq is not None:
                if np.shape(self.data) != np.shape(dq):
                    raise ValueError("The shape of dq is {0} while we are expecting shape {1}".format(dq.shape, self.data.shape))
                self.dq = dq
            else:
                self.dq = np.zeros(self.data.shape)

            # record when this file was created and with which version of the pipeline
            self.ext_hdr.set('DRPVERSN', corgidrp.version, "corgidrp version that produced this file")
            self.ext_hdr.set('DRPCTIME', time.Time.now().isot, "When this file was saved")


        # can do fancier things here if needed or storing more meta data

    # create this field dynamically
    @property
    def filepath(self):
        return os.path.join(self.filedir, self.filename)


    def save(self, filename=None, filedir=None):
        """
        Save file to disk with user specified filepath

        Args:
            filename (str): filepath to save to. Use self.filename if not specified
            filedir (str): filedir to save to. Use self.filedir if not specified
        """
        if filename is not None:
            self.filename = filename
        if filedir is not None:
            self.filedir = filedir

        if len(self.filename) == 0:
            raise ValueError("Output filename is not defined. Please specify!")

        prihdu = fits.PrimaryHDU(header=self.pri_hdr)
        exthdu = fits.ImageHDU(data=self.data, header=self.ext_hdr)
        hdulist = fits.HDUList([prihdu, exthdu])
        errhd = fits.Header()
        errhd["EXTNAME"] = "ERR"
        errhdu = fits.ImageHDU(data=self.err, header = errhd)
        hdulist.append(errhdu)
        dqhd = fits.Header()
        dqhd["EXTNAME"] = "DQ"
        dqhdu = fits.ImageHDU(data=self.dq, header = dqhd)
        hdulist.append(dqhdu)
        hdulist.writeto(self.filepath, overwrite=True)
        hdulist.close()

    def _record_parent_filenames(self, input_dataset):
        """
        Record what input dataset was used to create this Image.
        This assumes many Images were used to make this single Image.
        Record is stored in the ext header.

        Args:
            input_dataset (corgidrp.data.Dataset): the input dataset that were combined together to make this image
        """
        self.ext_hdr.set('DRPNFILE', len(input_dataset), "Number of files used to create this processed frame")
        for i, img in enumerate(input_dataset):
            self.ext_hdr.set('FILE{0}'.format(i), img.filename, "Filename of file #{0} used to create this frame".format(i))

    def copy(self, copy_data=True):
        """
        Make a copy of this image file. including data and headers.
        Data copying can be turned off if you only want to modify the headers
        Headers should always be copied as we should modify them any time we make new edits to the data

        Args:
            copy_data (bool): (optional) whether the data should be copied. Default is True

        Returns:
            corgidrp.data.Image: a copy of this Image
        """
        if copy_data:
            new_data = np.copy(self.data)
            new_err = np.copy(self.err)
            new_dq = np.copy(self.dq)
        else:
            new_data = self.data # this is just pointer referencing
            new_err = self.err
            new_dq = self.dq
        new_img = Image(new_data, pri_hdr=self.pri_hdr.copy(), ext_hdr=self.ext_hdr.copy(), err = new_err, dq = new_dq)

        # annoying, but we got to manually update some parameters. Need to keep track of which ones to update
        new_img.filename = self.filename
        new_img.filedir = self.filedir

        # update DRP version tracking
        self.ext_hdr['DRPVERSN'] =  corgidrp.version
        self.ext_hdr['DRPCTIME'] =  time.Time.now().isot

        return new_img

    def get_masked_data(self):
        """
        Uses the dq array to generate a numpy masked array of the data

        Returns:
            numpy.ma.MaskedArray: the data masked
        """
        mask = self.dq>0
        return ma.masked_array(self.data, mask=mask)

class Dark(Image):
    """
    Dark calibration frame for a given exposure time.

     Args:
        data_or_filepath (str or np.array): either the filepath to the FITS file to read in OR the 2D image data
        pri_hdr (astropy.io.fits.Header): the primary header (required only if raw 2D data is passed in)
        ext_hdr (astropy.io.fits.Header): the image extension header (required only if raw 2D data is passed in)
        input_dataset (corgidrp.data.Dataset): the Image files combined together to make this dark file (required only if raw 2D data is passed in)
    """
    def __init__(self, data_or_filepath, pri_hdr=None, ext_hdr=None, input_dataset=None):
        # run the image class contructor
        super().__init__(data_or_filepath, pri_hdr=pri_hdr, ext_hdr=ext_hdr)
        # additional bookkeeping for Dark

        # if this is a new dark, we need to bookkeep it in the header
        # b/c of logic in the super.__init__, we just need to check this to see if it is a new dark
        if ext_hdr is not None:
            if input_dataset is None:
                # error check. this is required in this case
                raise ValueError("This appears to be a new dark. The dataset of input files needs to be passed in to the input_dataset keyword to record history of this dark.")
            self.ext_hdr['DATATYPE'] = 'Dark' # corgidrp specific keyword for saving to disk

            # log all the data that went into making this dark
            self._record_parent_filenames(input_dataset)

            # add to history
            self.ext_hdr['HISTORY'] = "Dark with exptime = {0} s created from {1} frames".format(self.ext_hdr['EXPTIME'], self.ext_hdr['DRPNFILE'])

            # give it a default filename using the first input file as the base
            # strip off everything starting at .fits
            orig_input_filename = input_dataset[0].filename.split(".fits")[0]
            self.filename = "{0}_dark.fits".format(orig_input_filename)


        # double check that this is actually a dark file that got read in
        # since if only a filepath was passed in, any file could have been read in
        if 'DATATYPE' not in self.ext_hdr or self.ext_hdr['DATATYPE'] != 'Dark':
            raise ValueError("File that was loaded was not a Dark file.")

class NonLinearityCalibration(Image):
    """
    Class for non-linearity calibration files. Although it's not stricly an image that you might look at, it is a 2D array of data

     Args:
        data_or_filepath (str or np.array): either the filepath to the FITS file to read in OR the 2D image data
        pri_hdr (astropy.io.fits.Header): the primary header (required only if raw 2D data is passed in)
        ext_hdr (astropy.io.fits.Header): the image extension header (required only if raw 2D data is passed in)
        input_dataset (corgidrp.data.Dataset): the Image files combined together to make this dark file (required only if raw 2D data is passed in)
    """
    def __init__(self, data_or_filepath, pri_hdr=None, ext_hdr=None, input_dataset=None):
        # run the image class contructor
        super().__init__(data_or_filepath, pri_hdr=pri_hdr, ext_hdr=ext_hdr)
        # additional bookkeeping for Dark

        # if this is a new dark, we need to bookkeep it in the header
        # b/c of logic in the super.__init__, we just need to check this to see if it is a new dark
        if ext_hdr is not None:
            if input_dataset is None:
                # error check. this is required in this case
                raise ValueError("This appears to be a new Non Linearity Correction. The dataset of input files needs to be passed in to the input_dataset keyword to record history of this calibration file.")
            self.ext_hdr['DATATYPE'] = 'NonLinearityCalibration' # corgidrp specific keyword for saving to disk

            # log all the data that went into making this dark
            self._record_parent_filenames(input_dataset)

            # add to history
            self.ext_hdr['HISTORY'] = "Non Linearity Calibration file created"

            # give it a default filename using the first input file as the base
            # strip off everything starting at .fits
            orig_input_filename = input_dataset[0].filename.split(".fits")[0]
            self.filename = "{0}_NonLinearityCalibration.fits".format(orig_input_filename)


        # double check that this is actually a dark file that got read in
        # since if only a filepath was passed in, any file could have been read in
        if 'DATATYPE' not in self.ext_hdr or self.ext_hdr['DATATYPE'] != 'NonLinearityCalibration':
            raise ValueError("File that was loaded was not a NonLinearityCalibration file.")
        

datatypes = { "Image" : Image,
              "Dark"  : Dark,
              "NonLinearityCalibration" : NonLinearityCalibration }

def autoload(filepath):
    """
    Loads the supplied FITS file filepath using the appropriate data class

    Should be used sparingly to avoid accidentally loading in data of the wrong type

    Args:
        filepath (str): path to FITS file

    Returns:
        corgidrp.data.* : an instance of one of the data classes specified here
    """

    with fits.open(filepath) as hdulist:
        # check the exthdr for datatype
        if 'DATATYPE' in hdulist[1].header:
            dtype = hdulist[1].header['DATATYPE']
        else:
            # datatype not specified. Check if it's 2D
            if len(hdulist[1].data.shape) == 2:
                # a standard image (possibly a science frame)
                dtype = "Image"
            else:
                errmsg = "Could not determine datatype for {0}. Data shape of {1} is not 2-D"
                raise ValueError(errmsg.format(filepath, dtype))

    # if we got here, we have a datatype
    data_class = datatypes[dtype]

    # use the class constructor to load in the data
    frame = data_class(filepath)

    return frame
