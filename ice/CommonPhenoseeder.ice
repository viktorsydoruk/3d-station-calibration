#ifndef _COMMONPHENOSEEDER_ICE
#define _COMMONPHENOSEEDER_ICE


[["cpp:include:unordered_map"]]


module CommonPhenoseeder {

	//enum Unit{Metre, SquareMetre, CubicMetre, Kilogram, Dimensionless};

	enum ExperimentStatus{CREATED, RUNNING, FINISHED, UNKNOWN};

	struct TrayInformation{
		double intermediateAreaX;
		double intermediateAreaY;
		int numberOfPotsX;
		int numberOfPotsY;
		double offsetSeedingHeight;
		double offsetToBaseX;
		double offsetToBaseY;
		double offsetToBaseZ;
	};

	struct PotInformation{
		double potWidth;
		double potHeight;
		double potDepth;

	};

	//struct IntermediateArea{
	//	double x;
	//	double y;
	//};

	//struct TraySize{
	//	int col;
	//	int row;
	//};

	struct Measurement{
		string comment;
        double value;
        //CommonPhenoseeder::Unit unitType;
		int unitId;
		int traitId;
	};

	struct ImageResult
	{
		string FileName;
		int ImageTypeId;
		string Description;
	};

	struct Point{
		int x;
		int y;
	};
	
	sequence<Point> vecOfPoints;

	struct PotAllocation
	{
		long seedId;
		Point position;
	};

	sequence<PotAllocation> trayAllocation;

	// it is important to keep track of the order of insertion of the tray allocations 
	// different reasons for that... on the one hand: if you have a tray with lots of genotypes, u want
	// that they are worked off from left to right and on the other hand at program startup the information
	// at which point u paused the experiment is deterimend by Fischi (c# program) (because if I would 
	// determine it the safety cage needs to be close) and so the order is not irrelevant
	// std::map doesn't work because the keys are sorted
	// std::unordered_map doesn't work as well because it doesn't keep track of the order of insertion
	// because it is hashed and in the end you don't know who the key-value pairs are inserted
	// so u need an additional data structure for that...
	struct orderedMap{
		int first;
		//std::vector<int> coords;
		//int coords;
		vecOfPoints second;
	};

	
	// batches to tray coordinates
	sequence<orderedMap> vecOfOrderedMap;
	// tray to batch
	dictionary<int, vecOfOrderedMap> mapOfvecOfOrderedMap;

	//sequence<Point> vecOfPoints;
	//["cpp:type:std::unordered_map<Ice::Int, vecOfPoints>"] dictionary<int, vecOfPoints> mapOfIntToPointsVec;
	//dictionary<int, mapOfIntToPointsVec> mapOfMapOfIntToPointsVec;


	sequence<int> vecOfInts;
	sequence<double> vecOfDoubles;
	sequence<string> vecOfStrings;
	sequence<Measurement> vecOfMeasurements;
	sequence<ImageResult> vecOfImageResults;

	struct segmentationParams{
		int Hmin;
		int Hmax;
		int Smin;
		int Smax;
		int Vmin;
		int Vmax;
		int minSizeObj;
		int maxSizeObj;
		int minSizeHoles;
		int structureElement;
	};



};

#endif