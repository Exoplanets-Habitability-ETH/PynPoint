"""
Module for reading fits files coming from the VISIR instrument.
"""
import os
import sys
import subprocess
import threading
import warnings
import math

import numpy as np
import shlex
import six

from astropy.io import fits

from pynpoint.core.attributes import get_attributes
from pynpoint.core.processing import ReadingModule
from pynpoint.util.module import progress


class NearInitializationModule(ReadingModule):
    """
    This module reads the input fits files from the input directory and returns 4 outputs. These
    correspond to the specific chop/nod configuration. This module is desinged for NEAR data from
    the VISIR instrument.
    The fits files are multidimensional where the first hdulist contains only the general header.
    The second hdulist contains both data and a small header, where the data is a single frame and
    the small header contains specific information about this frame. This format continues until the
    last frame, which is an average of all frames.
    """

    def __init__(self,
                 name_in="burst",
                 image_in_dir="im_in",
                 image_out_tag_1="noda_chopa",
                 image_out_tag_2="noda_chopb",
                 image_out_tag_3="nodb_chopa",
                 image_out_tag_4="nodb_chopb",
                 scheme='ABBA',
                 check=True,
                 overwrite=True):
        """
        Constructor of the VisirBurtModule.

        Parameters
        ----------
        name_in : str
            Unique name of the instance.
        image_in_dir : str
            Entry directory of the database used as input of the module.
        image_out_tag_1 : str
            Entry written as output, Nod A -> Chop A.
        image_out_tag_1 : str
            Entry written as output, Nod A -> Chop B.
        image_out_tag_1 : str
            Entry written as output, Nod B -> Chop A.
        image_out_tag_1 : str
            Entry written as output, Nod B -> Chop B.
        scheme : str
            Scheme used when keyword ESO SEQ NODPOS is not found. Can be 'ABBA' or 'ABAB'
        check : bool
            Check all the listed non-static attributes or ignore the attributes that
            are not always required (e.g. PARANG_START, DITHER_X).
        overwrite : bool
            Overwrite existing data and header in the central database.

        Returns
        -------
        NoneType
            None
        """

        super(NearInitializationModule, self).__init__(name_in=name_in)

        # Port
        self.m_image_out_port_1 = self.add_output_port(image_out_tag_1)
        self.m_image_out_port_2 = self.add_output_port(image_out_tag_2)
        self.m_image_out_port_3 = self.add_output_port(image_out_tag_3)
        self.m_image_out_port_4 = self.add_output_port(image_out_tag_4)

        # Parameters
        self.m_im_dir = image_in_dir
        self.m_check = check
        self.m_overwrite = overwrite
        self.m_scheme = scheme

        # Arguments
        self.m_static = []
        self.m_non_static = []

        self.m_attributes = get_attributes()

        for key, value in six.iteritems(self.m_attributes):
            if value["config"] == "header" and value["attribute"] == "static":
                self.m_static.append(key)

        for key, value in six.iteritems(self.m_attributes):
            if value["attribute"] == "non-static":
                self.m_non_static.append(key)

        self.m_count = 0

    def _initialize(self):
        """
        Function that clears the __init__ tags if they are not empty given incorrect input.

        Returns
        -------
        NoneType
            None
        """

        tag = [self.m_image_out_port_1.tag,
               self.m_image_out_port_2.tag,
               self.m_image_out_port_3.tag,
               self.m_image_out_port_4.tag]

        seen = set()
        for i in tag:
            if i in seen:
                raise ValueError("Output ports should have different tags")
            if i not in seen:
                seen.add(i)

        if self.m_scheme != "ABBA" and self.m_scheme != "ABAB":
            raise ValueError("Scheme keyword should be set to 'ABBA' or 'ABAB'")

        if not isinstance(self.m_check, bool):
            raise ValueError("Check port should be set to 'True' or 'False'")

        if not isinstance(self.m_overwrite, bool):
            raise ValueError("Overwrite port should be set to 'True' or 'False'")

        if self.m_image_out_port_1 is not None:
            self.m_image_out_port_1.del_all_data()
            self.m_image_out_port_1.del_all_attributes()

        if self.m_image_out_port_2 is not None:
            self.m_image_out_port_2.del_all_data()
            self.m_image_out_port_2.del_all_attributes()

        if self.m_image_out_port_3 is not None:
            self.m_image_out_port_3.del_all_data()
            self.m_image_out_port_3.del_all_attributes()

        if self.m_image_out_port_4 is not None:
            self.m_image_out_port_4.del_all_data()
            self.m_image_out_port_4.del_all_attributes()

    def _static_attributes(self, fits_file, header, iteration, end):
        """
        Internal function which adds the static attributes to the central database.

        Parameters
        ----------
        fits_file : str
            Name of the FITS file.
        header : astropy.io.fits.header
            Header information from the FITS file that is read.
        iteration : int
            Iteration/Number of current fits file.
        end : int
            Total number of fits files.

        Returns
        -------
        NoneType
            None
        """

        a, b, c, d = 0, 0, 0, 0

        for item in self.m_static:

            if self.m_check:
                fitskey = self._m_config_port.get_attribute(item)

                if isinstance(fitskey, np.bytes_):
                    fitskey = str(fitskey.decode("utf-8"))

                if fitskey != "None":
                    if fitskey in header:
                        try:
                            status = self.m_image_out_port_1.check_static_attribute(item,
                                                                                    header[fitskey])
                        except KeyError:
                            # This only outputs the error for the last fits file,otherwise it spawns
                            if iteration == end and a == 0:
                                sys.stdout.write(
                                    "\n \033[93m The output tag {} is empty. There is no nodding "
                                    "postion A. Add input fit files that contain both nod A and "
                                    "nod B.\033[00m\n".format(self.m_image_out_port_1.tag))
                                sys.stdout.flush()

                                a = 1
                            else:
                                pass
                        try:
                            status = self.m_image_out_port_2.check_static_attribute(item,
                                                                                    header[fitskey])
                        except KeyError:
                            if iteration == end and b == 0:
                                sys.stdout.write(
                                    "\n \033[93m The output tag {} is empty. There is no nodding "
                                    "postion A. Add input fit files that contain both nod A and "
                                    "nod B.\033[00m\n".format(self.m_image_out_port_2.tag))
                                sys.stdout.flush()

                                b = 1
                            else:
                                pass
                        try:
                            status = self.m_image_out_port_3.check_static_attribute(item,
                                                                                    header[fitskey])
                        except KeyError:
                            if iteration == end and c == 0:
                                sys.stdout.write(
                                    "\n \033[93m The output tag {} is empty. There is no nodding "
                                    "postion B. Add input fit files that contain both nod A and "
                                    "nod B.\033[00m\n".format(self.m_image_out_port_3.tag))
                                sys.stdout.flush()

                                c = 1
                            else:
                                pass
                        try:
                            status = self.m_image_out_port_4.check_static_attribute(item,
                                                                                    header[fitskey])
                        except KeyError:
                            if iteration == end and d == 0:
                                sys.stdout.write(
                                    "\n \033[93m The output tag {} is empty. There is no nodding "
                                    "postion B. Add input fit files that contain both nod A and "
                                    "nod B.\033[00m\n".format(self.m_image_out_port_4.tag))
                                sys.stdout.flush()

                                d = 1
                            else:
                                pass

                        if status == 1:
                            with warnings.catch_warnings():
                                warnings.simplefilter("ignore")

                                self.m_image_out_port_1.add_attribute(item, header[fitskey],
                                                                      static=True)
                                self.m_image_out_port_2.add_attribute(item, header[fitskey],
                                                                      static=True)
                                self.m_image_out_port_3.add_attribute(item, header[fitskey],
                                                                      static=True)
                                self.m_image_out_port_4.add_attribute(item, header[fitskey],
                                                                      static=True)

                        if status == -1:
                            warnings.warn("Static attribute %s has changed. Possibly the current "
                                          "file %s does not belong to the data set '%s'. Attribute "
                                          "value is updated."
                                          % (fitskey, fits_file, self.output.tag))

                        elif status == 0:
                            pass

                    else:
                        warnings.warn("Static attribute %s (=%s) not found in the FITS header."
                                      % (item, fitskey))

    def _non_static_attributes(self, header):
        """
        Internal function which adds the non-static attributes to the central database.

        Parameters
        ----------
        header : astropy.io.fits.header
            Header information from the FITS file that is read.

        Returns
        -------
        NoneType
            None
        """

        for item in self.m_non_static:
            if self.m_check:
                if item in header:
                    self.m_image_out_port_1.append_attribute_data(item, header[item])
                    self.m_image_out_port_2.append_attribute_data(item, header[item])
                    self.m_image_out_port_3.append_attribute_data(item, header[item])
                    self.m_image_out_port_4.append_attribute_data(item, header[item])

                else:
                    if self.m_attributes[item]["config"] == "header":
                        fitskey = self._m_config_port.get_attribute(item)

                        if isinstance(fitskey, np.bytes_):
                            fitskey = str(fitskey.decode("utf-8"))

                        if fitskey != "None":
                            if fitskey in header:
                                self.m_image_out_port_1.append_attribute_data(item, header[fitskey])
                                self.m_image_out_port_2.append_attribute_data(item, header[fitskey])
                                self.m_image_out_port_3.append_attribute_data(item, header[fitskey])
                                self.m_image_out_port_4.append_attribute_data(item, header[fitskey])

    def _extra_attributes(self, fits_file, location, shape, nod):
        """
        Internal function which adds extra attributes to the central database.

        Parameters
        ----------
        fits_file : str
            Name of the FITS file.
        location : str
            Directory where the FITS file is located.
        shape : tuple(int)
            Shape of the images.

        Returns
        -------
        NoneType
            None
        """

        pixscale = self._m_config_port.get_attribute('PIXSCALE')

        if len(shape) == 2:
            nimages = 1
        elif len(shape) == 3:
            nimages = shape[0]

        index = np.arange(self.m_count, self.m_count + nimages, 1)

        for _, item in enumerate(index):
            if nod == 'A':
                self.m_image_out_port_1.append_attribute_data("INDEX", item)
                self.m_image_out_port_2.append_attribute_data("INDEX", item)
            elif nod == 'B':
                self.m_image_out_port_3.append_attribute_data("INDEX", item)
                self.m_image_out_port_4.append_attribute_data("INDEX", item)

        if nod == 'A':
            self.m_image_out_port_1.append_attribute_data("FILES", location + fits_file)
            self.m_image_out_port_2.append_attribute_data("FILES", location + fits_file)
            self.m_image_out_port_1.add_attribute("PIXSCALE", pixscale, static=True)
            self.m_image_out_port_2.add_attribute("PIXSCALE", pixscale, static=True)
        elif nod == 'B':
            self.m_image_out_port_3.append_attribute_data("FILES", location + fits_file)
            self.m_image_out_port_4.append_attribute_data("FILES", location + fits_file)
            self.m_image_out_port_3.add_attribute("PIXSCALE", pixscale, static=True)
            self.m_image_out_port_4.add_attribute("PIXSCALE", pixscale, static=True)
        else:
            warnings.warn("Attribute -nod- in function _extra_attribtutes is not A or B.")

        self.m_count += nimages

    def _uncompress_multi(self, filename):
        """
        Subfuction of -uncompress- used for threading. It uncompresses the file *filename*.

        Returns
        -------
        NoneType
            None
        """

        try:
            command = "uncompress " + filename
            subprocess.check_call(shlex.split(command))

        except (FileNotFoundError, OSError):
            # If command *uncompress* is not existing

            command = "gunzip -d " + filename
            subprocess.check_call(shlex.split(command))

    def uncompress(self):
        """
        This function checks the input directory if it contains any compressed files ending with
        '.fits.Z'. If this is the case, it will uncompress these using multithreading. This is much
        faster than uncompressing when having multiple files.

        Returns
        -------
        NoneType
            None
        """

        cpu = self._m_config_port.get_attribute("CPU")

        location = os.path.join(self.m_im_dir, '')
        files = os.listdir(location)
        files_compressed = []

        for f in files:
            if f.endswith('.fits.Z'):
                files_compressed.append(os.path.join(location, f))

        if not files_compressed:
            # No files have to be uncompressed
            pass

        else:
            sys.stdout.write("\rRunning NEARInitializationModule... ")
            sys.stdout.write("\nUncompressing input files... ")
            sys.stdout.flush()

            no_files = len(files_compressed)

            for i in range(math.ceil(no_files / cpu)):
                last_file = min(cpu * (i + 1), no_files + 1 - (cpu * i), no_files)
                files_compressed_chunk = files_compressed[cpu * i:last_file]
                progress(i, math.ceil(no_files / cpu), "\rUncompressing input files...")

                jobs = []
                for i, filename in enumerate(files_compressed_chunk):
                    thread = threading.Thread(target=self._uncompress_multi, args=(filename,))
                    jobs.append(thread)

                for j in jobs:
                    j.start()

                for j in jobs:
                    j.join()

    def check_header(self, head):
        """
        Check general header keywords and prompt warning if the value is other than default.

        Returns
        -------
        NoneType
            None
        """

        chop_enabled = str(head['ESO DET CHOP ST'])
        if chop_enabled == 'F':
            warnings.warn("Chopping has been set to disabled")

        skipped = int(head['ESO DET CHOP CYCSKIP'])
        if skipped != 0:
            warnings.warn("{} chop cycles have been skipped during operation.".format(skipped))

        half_cycle = str(head['ESO DET CHOP CYCSUM'])
        if half_cycle == 'T':
            warnings.warn("Frames have been averaged by default. This module will probably not "
                          "work properly")

    def open_fit(self, location, image_file, number):
        """
        Function that opens the fit file at --location + image_file--. It returns the input image
        file into chop A and chop B, including the header data.
        The first hdulist only contains the general header, the last an average of all images.

        Returns
        -------
        chopa : numpy array
            Array containing all chop A images.
        chopb : numpy array
            Array containing all chop B images.
        nod : str
            String with 'A' or 'B', denoting the nod type.
        head : astropy.io.fits.header
            General header valid for all images.
        head_small : astropy.io.fits.header
            Header of the first frame, containing frame specific information.
        images.shape : array
            Shape of the input array.
        """

        hdulist = fits.open(location + image_file)
        image = hdulist[1].data.byteswap().newbyteorder()

        nimages = len(hdulist) - 2
        head = hdulist[0].header
        head_small = hdulist[1].header

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")

            header = head.copy()
            header.update(head_small)
            header.insert(3, ('NAXIS', 3))
            header.insert(4, ('NAXIS1', int(head_small['NAXIS1'])))
            header.insert(4, ('NAXIS2', int(head_small['NAXIS2'])))
            header.insert(5, ('NAXIS3', int(nimages)))

        try:
            nod = header['ESO SEQ NODPOS']

        except KeyError:
            if number == 0:
                warnings.warn("Keyword 'ESO SEQ NODPOS' cannot be found. Assuming {} nod "
                              "scheme".format(self.m_scheme))

            if self.m_scheme == "ABBA":
                if (number % 4) == 0 or (number % 4) == 3:
                    nod = 'A'

                if (number % 4) == 1 or (number % 4) == 2:
                    nod = 'B'

            elif self.m_scheme == "ABAB":
                if (number % 2) == 0:
                    nod = 'A'

                if (number % 2) == 1:
                    nod = 'B'

        self.check_header(header)

        # Initialize the max possible size for chopa/b
        chopa = np.zeros((int(nimages), image.shape[0], image.shape[1]), dtype=np.float32)
        chopb = np.zeros((int(nimages), image.shape[0], image.shape[1]), dtype=np.float32)

        images = np.zeros((nimages, image.shape[0], image.shape[1]))
        for i in range(1, nimages + 1):
            images[i - 1, :, :] = hdulist[i].data.byteswap().newbyteorder()

        count_im_1, count_im_2 = 0, 0

        for i in range(0, nimages):
            cycle = hdulist[i + 1].header['HIERARCH ESO DET FRAM TYPE']

            if cycle == 'HCYCLE1':
                chopa[count_im_1, :, :] = images[i, :, :]
                count_im_1 += 1

            elif cycle == 'HCYCLE2':
                chopb[count_im_2, :, :] = images[i, :, :]
                count_im_2 += 1

            else:
                warnings.warn("The chop position(=HIERARCH ESO DET FRAM TYPE) could not be found"
                              "from the header(small). Iteration: {}".format(i))

        # Remove the frames that were kept zero
        chopa = chopa[chopa[:, 0, 0] != 0, :, :]
        chopb = chopb[chopb[:, 0, 0] != 0, :, :]

        if len(chopa[:, ]) != len(chopb[:, ]):
            warnings.warn("The number of frames is not equal for chopa and chopb")

        fits_header = []
        for key in header:
            fits_header.append(str(key)+" = "+str(header[key]))

        hdulist.close()

        header_out_port = self.add_output_port('fits_header/' + image_file)
        header_out_port.set_all(fits_header)

        return chopa, chopb, nod, header, images.shape

    def run(self):
        """
        Run the module. The module first checks the tags for uniquenes. The fit files from the
        input-dir are collected, each ran with the  - self.open_fit() - function. This outputs the
        data into 2 parts, chop location A and B. The nod-tag will tell from the header from which
        nod location this chop A&B comes from. This is appended to the output tags. The output tags
        correspond to nod A -> chop A & B, nod B -> chop A & B - respectively.
        Lastly, from the header, the cards are inported to the general config port of PynPoint.

        Returns
        -------
        NoneType
            None
        """

        self._initialize()

        # Check if the files are compressed, if so; uncompress
        self.uncompress()

        sys.stdout.write("\rRunning NEARInitializationModule...")
        sys.stdout.flush()

        # Open each fit file
        location = os.path.join(self.m_im_dir, '')

        files = []
        for filename in os.listdir(location):
            if filename.endswith('.fits'):
                files.append(filename)

        files.sort()

        assert(files), "No FITS files found in {}".format(self.m_im_dir)

        for i, im in enumerate(files):
            progress(i, len(files), "\rRunning NEARInitializationModule...")

            chopa, chopb, nod, header, shape = self.open_fit(location, im, i)

            if nod == "A":
                self.m_image_out_port_1.append(chopa, data_dim=3)
                self.m_image_out_port_2.append(chopb, data_dim=3)

            if nod == "B":
                self.m_image_out_port_3.append(chopa, data_dim=3)
                self.m_image_out_port_4.append(chopb, data_dim=3)

            # Collect header data
            self._static_attributes(files[i], header, i, len(files) - 1)
            self._non_static_attributes(header)
            self._extra_attributes(files[i], location, shape, nod)

            # Only flush when output ports contain new data
            if nod == "A":
                self.m_image_out_port_1.flush()
                self.m_image_out_port_2.flush()
            if nod == "B":
                self.m_image_out_port_3.flush()
                self.m_image_out_port_4.flush()

        sys.stdout.write("\rRunning NearInitializationModule... [DONE]\n")
        sys.stdout.flush()

        self.m_image_out_port_1.add_history("NearInitializationModule", "Nod A, Chop A")
        self.m_image_out_port_2.add_history("NearInitializationModule", "Nod A, Chop B")
        self.m_image_out_port_3.add_history("NearInitializationModule", "Nod B, Chop A")
        self.m_image_out_port_4.add_history("NearInitializationModule", "Nod B, Chop B")
        self.m_image_out_port_1.close_port()
        self.m_image_out_port_2.close_port()
        self.m_image_out_port_3.close_port()
        self.m_image_out_port_4.close_port()
