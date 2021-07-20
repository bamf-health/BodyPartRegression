# Body Part Regression 

The Body Part Regression (BPR) model translates the anatomy in a radiologic volume into a machine-readable form. 
Each axial slice maps to a slice score. The slice scores monotonously increase with patient height. 
With the help of a slice-score look-up table, the mapping between certain landmarks to slice scores can be checked. 
The BPR model learns in a completely self-supervised fashion. There is no need for annotated data for training the model instead of evaluation purposes. 

The BPR model can be used for sorting and labeling radiologic images by body parts. Moreover, it is useful for cropping specific body parts as a pre-processing or post-processing step of medical algorithms. If a body part is invalid for a certain medical algorithm, it can be cropped out before applying the algorithm to the volume. 

The Body Part Regression model in this repository is based on the SSBR model from [Yan et al.](https://arxiv.org/pdf/1707.03891.pdf) 
with a few modifications explained in the master thesis "Body Part Regression for CT Volumes". 

For CT volumes, a pretrained model for inference exists already. 
With a simple command from the terminal, the body part information can be calculated for nifti-files.  


--------------------------------------------------------------
## Install package 

1. Create a new virtual environment with pip
2. Clone the bodypartregression repsoitory from phabricator 
3. Go into the bodypartregression/ folder and run: 
   
```bash
pip install -e .
```

--------------------------------------------------------------
## Analyze examined body parts
The scope of the pretrained BPR model for CT volumes are body parts from adults from the beginning of the pelvis to the end of the head. Note that due to missing training data, children, pregnant women or legs are not in the scope of the algorithm. <br> 
To obtain the body part information for nifti-files you need to provide the nifti-files with the file ending *.nii or *.nii.gz in one directory and run the following command: 
```bash
bpreg_predict -i <input_path> -o <output_path>
``` 
Tags for the `bpreg_predict` command: <br>
- `-i` (str): input path, origin of nifti-files
- `-o` (str): save path for created meta-data json-files
- `--skip` (bool): skip already created .json metadata files (default: 1) <br>
- `--model` (str): specify model (default: public model from zenodo for CT volumes)


Through the `bpreg_predict` command for each nifti-file in the directory `input_path` a corresponding json-file 
gets created and saved in the `output_path`. <br>

If you use this model for your work, please make sure to cite the model and the training data as explained at 
[zenodo](https://zenodo.org/record/5113483#.YPaBkNaxWEA). 


--------------------------------------------------------------
## Structure of metadata file

The json-file contains all the metadata regarding the examined body part of the nifti-file. It includes the following  tags: 
- `cleaned slice-scores`: Cleanup of the outcome from the BPR model (smoothing, filtering out outliers). 
- `unprocessed slice-scores`: Plain outcome of the BPR model. 
- `body part examined`: Dictionary with the tags: "legs", "pelvis", "abdomen", "chest", "shoulder-neck" and "head". For each body-part, the slice indices are listed, where the body part is visible. 
- `body part examined tag`: updated tag for BodyPartExamined. Possible values: PELVIS, ABDOMEN, CHEST, NECK, HEAD, HEAD-NECK-CHEST-ABDOMEN-PELVIS, HEAD-NECK-CHEST-ABDOMEN, ... 
- `look-up table`: reference table to be able to map slice scores to landmarks and vise versa. 
- `reverse z-ordering`: (0/1) equal to one if patient height decreases with slice index. 
- `valid z-spacing`: (0/1) equal to one if z-spacing seems to be plausible. The data sanity check is based on the slope of the curve from the cleaned slice-scores.

The information from the meta-data file can be traced back to the `unprocessed slice-scores` and the `look-up table`. 


