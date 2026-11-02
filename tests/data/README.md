# Test data

`CalibrationAllPoints.dat` is a stored point cloud produced by the image-analysis
stage (`store_all_points`). It is used as a deterministic regression fixture for
the calibration fit, so the tests do not need the original TIFF images.

The file contains 500 observations; 8 have invalid radius/sigma values and are
filtered out by the normal pipeline, leaving 492 observations for the fit.
