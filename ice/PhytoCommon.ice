// Phyto common data structures
// Version: $Id: PhytoCommon.ice 1 2015-01-30 11:35:10Z j.roussel $


#ifndef _PHYTOCOMMON_ICE
#define _PHYTOCOMMON_ICE

#include <Ice/SliceChecksumDict.ice>
#include "PhytoError.ice"

module Phyto {

  module Common {
    //number of ticks from 1. January 0001 midnight until 1. january 1970 midnight in UTC time
    //needed because c++ IceUtil::Time start on 1. january 1970
    //UTC to local time must be done manually because IceUtil::Time has no function for that
	const long ticksto1970 = 621355932000000000;
  
	///////////////////////////////////////////////////////////////////////////////////////////////////////
	//		enums
	///////////////////////////////////////////////////////////////////////////////////////////////////////
	
	// enum for the different ice data types
	enum DATATYPES {DTUNSPECIFIED,DTICELONG,DTIMAGEDATA,DTACQDATA,DTICEDOUBLE};

    // enumeration for image type
	enum IMAGEFORMAT {PMUNKNOWN, PMBW, PMRGB, PMBGR, PMBGGR, PMRGGB, PMGRBG, PMGBRG
		, PMHSV, PMTHERMO, PMDISPARITY, PMDEPTH, PMSEGMENTATION, PMOPTICALFLOW
		, PMDENSEDISPARITY, PMGRAPH, PMYUV, PM3DIMAGE};

    // enumeration for image data type (denotes wich data array to use)
	enum IMAGEDATATYPE {IDTUNKNOWN, IDTBOOL, IDTBYTE, IDTSHORT, IDTFLOAT, IDTDOUBLE};
		
	enum BOOLFLAG
	{
		BFUNHANDLED,BFUNKNOWN,BFTRUE,BFFALSE
	};
  
	enum INTRINSICMODEL
	{
		INTRINSICUNKNOWN, 
		INTRINSICFFSPP,			//focusx, focusy, skew, pptx, ppty
		INTRINSICMATRIX			//3x3 matrix of intrinsic row aligned ({focusx skew pptx},{0 focusy ppty},{0 0 1})
	};
  
	enum EXTRINSICMODEL
	{
		EXTRINSICUNKNOWN,
		EXTRINSICEULER,			//Tx,Ty,Tz,Rz,Ry,Rx
		EXTRINSICRODRIGUES,		//Tx,Ty,Tz,r1,r2,r3
		EXTRINSICROTMATRIX		//Tx,Ty,Tz,9 values for 3x3 rotationmatrix row aligned
	};

	enum COORDINATESYSTEM
	{
		WORLD,			/*roboter base*/
		TOOL,			//roboter tool (e.g. calibrated with KUKA, including cameras)
		BASE,			//roboter base (calibrated with KUKA)
		CAM				//camera in current acquisitiondata (e.g. for relative extrinsics)
	};

	enum ENVIRONMENTPARAMETER
	{
		ENVIRONMENTUNNKNOWN,		
		ENVIRONMENTLIGHT,
		ENVIRONMENTAIRTEMPERATURE,
		ENVIRONMENTSOILTEMPERATURE,
		ENVIRONMENTAIRHUMIDITY,
		ENVIRONMENTSOILHUMIDITY,		
	};
	///////////////////////////////////////////////////////////////////////////////////////////////////////
	//		datastructures
	///////////////////////////////////////////////////////////////////////////////////////////////////////
	//sequence of timestamps
	sequence<long> timeStamps;			//=> CHANGE TO timeStampList
	
    // Vector of some basic slice types
    sequence<bool> boolVec;
    sequence<byte> byteVec;
    sequence<short> shortVec;
    sequence<float> floatVec;
    sequence<double> doubleVec;
    
    // Intrinsic camera parameters
    struct intrinsicParams {
      INTRINSICMODEL modelId = INTRINSICUNKNOWN;      
      Common::doubleVec modelParams;
    };

    sequence<intrinsicParams> intrinsicParamsVec;

    // Extrinsic camera parameters
    // all values are measured in mm !
	struct extrinsicParams {
	  EXTRINSICMODEL modelId = EXTRINSICUNKNOWN;
	  BOOLFLAG isAbsolute = BFUNHANDLED;		//Flag to indicate if extrinsic is absolute or relative
	  COORDINATESYSTEM coordsys = CAM;			//standard coordsystem is first Camera in current acquisitionData
	  int coordSysIndex = 0;					//only used for TOOL, CAM, BASE CoordSystem
      Common::doubleVec modelParams;
	};

	sequence<extrinsicParams> extrinsicParamsVec;
 
    // camera parameters   
    struct cameraParams {
      intrinsicParams intrinsicCameraParams;
      extrinsicParams extrinsicCameraParams;
    };

	sequence<cameraParams> cameraParamsVec;

    // Image data structure
    struct imageData {
      long timeNbr;	/* timestamp represented as number of ticks (100ns) since 00:00:00 Jan 1 0001*/
      int height;         // Image height
      int width;          // Image width
      int spp;            // Number of samples per pixel
      IMAGEFORMAT imgformat = PMUNKNOWN;	  // Image format (BW/RGB/BAYER...)
	  IMAGEDATATYPE imgDataType = IDTUNKNOWN; // Image data type (bool,byte,float...)
      int cameraId;       // Camera Id
      cameraParams virtualCamParams;			//ex-intrinsic of virtual cam (after image transformations e.g. rectification, undistortion)
      boolVec boolPixels; // Image pixel values (bool)
      byteVec bytePixels; // Image pixel values (byte)
      shortVec shortPixels; // Image pixel values (short)
      floatVec floatPixels; // Image pixel values (float)
    };

    sequence<imageData> imageFrames;

		struct treatment {
			long timestamp;			/* timeof treatment*/
			double value;			// value of treatment (e.g. amount of water, nutrition, ...)
		};
		
		["clr:generic:List"]sequence<treatment> treatmentVec;
		
		
		

		//parameter structure for output
		struct leaf {
			int no;
			int size;
		};
		
		sequence<leaf> leaveslist;
		
		//plantgraph describe complete plant (single leaves etc...)
		//IMPORTANT: timeNbr must be acquisition time of images which are used 
		//to calculate the graph
		struct plantgraph {
			long plantID;		/*ID of plant*/
			long timeNbr;		//timestamp
			leaveslist nodes;		//list of leaves
			//connection ???
			//plant treatments ???
			treatmentVec water;	//vector of water amount and time
		};
		
		sequence<plantgraph> graphlist;
		
		//numerical plantquantities
		struct plantQuantities {
			long plantID;
			long timeNbr;			//timestamp
			long germinationDate;	//timestamp of germination data
			// growth rate per leaf
			// leaf emergence rate
			// plant motility per leaf
			//double plantsize;
			//double wateruptake;

			double nbrOfLeaves;			//number of leaves
			double nbrOfGreenLeaves;		
			double nbrOfYellowLeaves;

			double meanLeafSize;			//classIndex of leafsize (can be looked up in module for numeric to symbolic mapping)
			double smallestLeafSize;
			double largestLeafSize;

			double plantTallness;

			double meanGrowthRate;
			double largestLeafGrowthRate;		//QUESTION: is this the growth rate of the largest leaf or the largest growth rate of some leaf

			//environmental values
			double airTemperature;
			double airHumidity;
			double lightIntensity;			// in µmol per plant
			double percentageOfLight;		// % of LED lights

		};

		//symbolic plantstate => mapped from numerical plantQuantities
		struct plantState
		{
			long plantID;		//ID of plant
			long timeNbr;		//timestamp
			long mappingID;		//ID of specific mapping (table)

			//plant block

			int nbrOfLeaves;			//number of leaves
			int nbrOfGreenLeaves;		
			int nbrOfYellowLeaves;

			int meanLeafSize;			//classIndex of leafsize (can be looked up in module for numeric to symbolic mapping)
			int smallestLeafSize;
			int largestLeafSize;

			int plantTallness;

			int meanGrowthRate;
			int largestLeafGrowthRate;		//QUESTION: is this the growth rate of the largest leaf or the largest growth rate of some leaf

			//possible features for future usage
			//int leafEmergenceRate;

			//environment block

			int airHumidity;
			int airTemperature;
			int lightIntensity;

			//possible features for future usage
			//int soilHumidity;
			//int soilTemperature;
		};

		enum ACTIONTYPE {WATERING ,NURTURE, LIGHT };

		struct numericAction
		{
			ACTIONTYPE type;
			long executionTime = -1;		//-1 (or anything in the past) means NOW
											// -1 allows for arbitrary execution order!
											// anything else will be executed chronologically
			float value;					// e.g. amount of water/nutrition
		};

		sequence<numericAction> numericActionList;

		/*struct environmentInfo
		{
			ENVIRONMENTPARAMETER type;
			double value;
		};

		sequence<environmentInfo> environmentInformations;*/
		dictionary<ENVIRONMENTPARAMETER, double> environmentInfo;
  };  /* End of Common module*/

};  /* End of Phyto module*/

#endif /* _PHYTOCOMMON_ICE*/
