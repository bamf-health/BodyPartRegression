import numpy as np
import nibabel as nib
import cv2
import os, sys, datetime

import matplotlib.pyplot as plt
import pandas as pd
from tqdm import tqdm
import albumentations as A
from scipy.ndimage import gaussian_filter
import pytorch_lightning as pl


class Nifti2Npy:
    """Convert nifti files to numpy arrays

    Args:
        target_pixel_spacing (float, optional): Target pixel spacing in the xy-plane for npy-array. Defaults to 3.5.
        min_hu (float, optional): min HU-value, all lower values will be set to the min-value . Defaults to -1000.0.
        max_hu (float, optional): max HU-value, all higher values will be set to the max-value. Defaults to 1500.0.
        ipath (str, optional): input path of nifti-files. Defaults to "/home/AD/s429r/Documents/Data/DataSet/Images/".
        opath (str, optional): output path for npy-files. Defaults to "/home/AD/s429r/Documents/Data/DataSet/Arrays-3.5mm/".
        size (int, optional): width and height for npy-array (size, size, z). Defaults to 128.
        skip_slices (int, optional): Skip conversion, if number of slices is less then skip_slices. Defaults to 30.
        corrupted_files (list[str], optional): skip files in this list. Defaults to [].
        reverse_zaxis (list[str], optional): flip z-axis for files in this list. Defaults to [].
        sigma (tuple[float], optional): variance for gaussian blurring (before downsampling), 
        if downsampling factor is equal to the reference_downsampling_factor. Defaults to (0.8, 0.8, 0).
        reference_downscaling_factor (float, optional): reference downsampling factor for sigma. Defaults to 0.25.
    """
    def __init__(
        self,
        target_pixel_spacing: float = 3.5,
        min_hu: float = -1000.0,
        max_hu: float = 1500.0,
        ipath: str = "/home/AD/s429r/Documents/Data/DataSet/Images/",
        opath: str = "/home/AD/s429r/Documents/Data/DataSet/Arrays-3.5mm/",
        size: int = 128,
        skip_slices: int = 30,
        corrupted_files: list = [],
        reverse_zaxis: list = [],
        sigma: tuple = (0.8, 0.8, 0),
        reference_downscaling_factor: float = 0.25,
    ):
        self.ipath = ipath
        self.opath = opath
        self.target_pixel_spacing = target_pixel_spacing
        self.min_hu = min_hu
        self.max_hu = max_hu
        self.size = size
        self.padding = A.PadIfNeeded(
            min_height=size,
            min_width=size,
            always_apply=True,
            border_mode=cv2.BORDER_CONSTANT,
        )
        self.center_crop = A.CenterCrop(p=1, height=size, width=size)
        self.corrputed_files = corrupted_files
        self.reverse_zaxis = reverse_zaxis
        self.skip_slices = skip_slices

        self.sigma = sigma
        self.reference_downscaling_factor = reference_downscaling_factor

    def reorder_volume(self, x, pixel_spacings, affine, filename):
        axis_ordering = self.get_axis_ordering(affine)

        # check axis ordering
        if list(axis_ordering) != [0, 1, 2]:
            x = np.transpose(x, np.argsort(axis_ordering))
            pixel_spacings = pixel_spacings[np.argsort(axis_ordering)]

        # check z-axis
        if (np.sign(affine[:, 2][axis_ordering == 2])[0] == -1) or (
            filename.startswith(tuple(self.reverse_zaxis))
        ):
            x = np.flip(x)

        return x, pixel_spacings

    def test_pixelspacing(self, pixel_spacings):
        if np.sum(pixel_spacings) > 10:
            print(f"Unusual pixel spacings: {pixel_spacings}!")
            return 1
        return 0

    def remove_empty_slices(self, x):
        nonzero_entries = np.where(np.sum(x, axis=(0, 1)) != 0)[0]
        x = x[:, :, np.unique(nonzero_entries)]
        return x

    def resize_volume(self, x, pixel_spacings):
        x = self.resize_xy(x, pixel_spacings)

        if (x.shape[0] < self.size) or (x.shape[1] < self.size):
            x = self.padding3d(x)
        if (x.shape[0] > self.size) or (x.shape[1] > self.size):
            x = self.center_crop(image=x)["image"]

        return x

    def test_volume(self, x):
        if (x.shape[0] != self.size) or (x.shape[1] != self.size):
            raise ValueError(f"Wrong image size: {x.shape}!")

    def dataframe_template(self, filepaths):
        filenames = [f.split("/")[-1] for f in filepaths]
        df = pd.DataFrame(
            index=filenames,
            columns=[
                "nii2npy",
                "x0",
                "y0",
                "z0",
                "x",
                "y",
                "z",
                "min_x",
                "max_x",
                "pixel_spacingx",
                "pixel_spacingy",
                "pixel_spacingz",
            ],
        )
        df["nii2npy"] = 0
        df["target_pixel_spacing"] = self.target_pixel_spacing
        df["min_hu"] = self.min_hu
        df["max_hu"] = self.max_hu
        return df

    def padding3d(self, x):
        if x.shape[2] > 800:
            y1 = self.padding(image=x[:, :, :400])["image"]
            y2 = self.padding(image=x[:, :, 400:800])["image"]
            y3 = self.padding(image=x[:, :, 800:])["image"]
            y = np.concatenate((y1, y2, y3), axis=2)

        elif x.shape[2] > 400:
            y1 = self.padding(image=x[:, :, :400])["image"]
            y2 = self.padding(image=x[:, :, 400:800])["image"]
            y3 = self.padding(image=x[:, :, 800:])["image"]
            y = np.concatenate((y1, y2), axis=2)
        else:
            y = self.padding(image=x)["image"]

        return y

    def rescale_xy(self, x):
        x = np.where(x > self.max_hu, self.max_hu, x)
        x = np.where(x < self.min_hu, self.min_hu, x)
        x = x - self.min_hu
        x = x * 255 / (self.max_hu - self.min_hu)
        return x

    def resize_xy(self, x, pixel_spacings):

        scalex = self.target_pixel_spacing / pixel_spacings[0]
        scaley = self.target_pixel_spacing / pixel_spacings[1]

        rescaled_sizex = int(x.shape[0] / scalex + 0.5)
        rescaled_sizey = int(x.shape[1] / scaley + 0.5)

        downscaling_factor_x = rescaled_sizex / x.shape[0]
        downscaling_factor_y = rescaled_sizey / x.shape[1]

        sigma = (
            self.sigma[0] * self.reference_downscaling_factor / downscaling_factor_x,
            self.sigma[1] * self.reference_downscaling_factor / downscaling_factor_y,
            0,
        )

        resize = A.Compose([A.Resize(int(rescaled_sizex), int(rescaled_sizey))])

        # add gaussian blure before downsampling to reduce artefacts
        x = gaussian_filter(x, sigma=sigma, truncate=3)
        y = resize(image=x)["image"]

        return y

    def add_baseinfo2df(self, df, filename, x):
        df.loc[filename, ["x0", "y0", "z0"]] = x.shape
        df.loc[filename, ["min_x", "max_x"]] = np.min(x), np.max(x)
        return df

    def add_info2df(self, df, filename, x, pixel_spacings):
        df.loc[
            filename, ["pixel_spacingx", "pixel_spacingy", "pixel_spacingz"]
        ] = pixel_spacings
        df.loc[filename, ["x", "y", "z"]] = x.shape
        df.loc[filename, "nii2npy"] = 1
        return df

    def get_axis_ordering(self, affine):
        """
        Get axis ordering of volume.
        """
        indices = np.argmax(np.abs(affine), axis=0)
        return indices.astype(int)

    def load_volume(self, filepath):
        img_nii = nib.load(filepath)
        try:
            x = img_nii.get_fdata(dtype=np.float32)
        except EOFError:
            print(f"Corrupted file {filepath}")
            return None, None, None
        pixel_spacings = np.array(list(img_nii.header.get_zooms()))
        affine = img_nii.affine[:3, :3]

        x, pixel_spacings = self.reorder_volume(x, pixel_spacings, affine, filepath.split("/")[-1])

        return x, pixel_spacings

    def preprocess_nifti(self, filepath):
        x, pixel_spacings= self.load_volume(filepath)
        x = self.rescale_xy(x)
        x = self.resize_volume(x, pixel_spacings)
        return x, pixel_spacings

    def convert_file(self, filepath, save=False):
        filename = filepath.split("/")[-1]
        ofilepath = (
            self.opath + filename.replace(".nii", "").replace(".gz", "") + ".npy"
        )

        x0, pixel_spacings = self.load_volume(filepath)
        if not isinstance(x0, np.ndarray):
            return None, None, None

        check = self.test_pixelspacing(pixel_spacings)
        if check == 1:
            return None, None, None
        if (
            (x0.shape[0] < self.skip_slices)
            or (x0.shape[1] < self.skip_slices)
            or (x0.shape[2] < self.skip_slices)
        ):
            print(f"Not enough slices {x0.shape}. Skip file.")
            return None, None, None
        if len(x0.shape) > 3:
            print(f"Unknown dimensions {x0.shape}. Skip file.")
            return None, None, None

        x = self.rescale_xy(x0)
        x = self.resize_volume(x, pixel_spacings)
        x = self.remove_empty_slices(x)
        self.test_volume(x)

        if save:
            np.save(ofilepath, x.astype(np.float32))
        return x, x0, pixel_spacings

    def convert(self, filepaths, save=False):
        df = self.dataframe_template(filepaths)

        for filepath in tqdm(filepaths):
            filename = filepath.split("/")[-1]
            if filepath in self.corrputed_files:
                continue
            x, x0, pixel_spacings = self.convert_file(filepath, save=save)
            if isinstance(x, np.ndarray):
                df = self.add_baseinfo2df(df, filename, x0)
                df = self.add_info2df(df, filename, x, pixel_spacings)

        return df
