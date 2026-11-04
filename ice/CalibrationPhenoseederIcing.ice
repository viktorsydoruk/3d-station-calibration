
#ifndef CALIBRATIONPHENOSEEDERICING_ICE
#define CALIBRATIONPHENOSEEDERICING_ICE

#include "CommonPhenoseeder.ice"
#include "PhytoCommon.ice"

module Phenoseeder
{
	sequence<string> stringSeq;
	//represents a point (e.g. robot coordinate)
	struct Point
	{
		double x;
		double y;
		double z;
	};

	//List of doubles (e.g. for error values)
	sequence<double> DoubleSeq;

	

	interface CalibrationPhenoseederIcing
	{
		//method which was still her => no idea what it is used for, but first I will not delete it
		void calibrate(int numberOfPoints, int shutter, int gain, int ubV, int vrV, int offsetX, int offsetY, int HMin, int HMax, int SMin, int SMax, int VMin, int VMax, int minSizeObj, int maxSizeObj, int minSizeHoles, Phyto::Common::imageData mask, int h, int w, double c, double z, double centralPointX, double centralPointY, double radius, int tool, out CommonPhenoseeder::vecOfDoubles HMatrix);
	

		//init with file or use std file (toml format)
		//returns the path of the folder where the calibration data is stored
		string init(int procedureId, optional(1) string configurationfilepath);

		//sent new point, image to calibration server		
		void addData(Point robotCoord, Phyto::Common::imageData image);

		//if is ready returns is true, no more data is needed and the results can be retrieved
		bool isReady();

		//get intrinsic and error
		void getIntrinsic(out Phyto::Common::intrinsicParams intrinsic,out DoubleSeq error);

		//get extrinsic (error should contain the errrors of rotation followed by the translation errors)
		void getExtrinsic(out Phyto::Common::extrinsicParams extrinsic,out DoubleSeq error);

		//get the distortion coefficients and the error
		void getDistortion(out DoubleSeq distortion,out DoubleSeq error);

		//get optimal nozzle center
		void getOptimalNozzlePosition(out Point nozzleCenter);

	};
};

#endif