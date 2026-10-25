"""Verify/fetch the official pretrained pose model for the separate pose runtime."""
from pathlib import Path
from setup_assets import download, ROOT

ASSET=dict(url='https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task',
           sha256='5134a3aad27a58b93da0088d431f366da362b44e3ccfbe3462b3827a839011b1')
if __name__=='__main__':
    download(ASSET,ROOT/'weights/pose_landmarker_full.task')
