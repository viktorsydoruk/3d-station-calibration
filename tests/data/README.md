# Test data

`CalibrationAllPoints.dat` is a stored point cloud produced by the image-analysis
stage (`store_all_points`). It is used as a deterministic regression fixture for
the calibration fit, so the tests do not need the original TIFF images.

The file contains 500 observations; 8 have invalid radius/sigma values and are
filtered out by the normal pipeline, leaving 492 observations for the fit.

`CeramicAllPoints.dat` is the stored point cache of the ceramic-ball folder
`P:\3Dcalibration\3D_small_20260929_ceramic`, including the covariance columns.
It contains 500 observations; 11 have invalid radius/sigma values, leaving 489
observations. `test_ceramic_regression.py` fits the production pinhole
configuration (`n_distortion_coefs=0`, `center_weighting=true`,
`max_outliers=10`) and checks the result against the folder's stored
`output/calibration_data.yaml`.
