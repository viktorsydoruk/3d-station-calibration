// SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
// SPDX-License-Identifier: Apache-2.0
//
// Local compatibility definition used until the shared PhytoCommon.ice from the
// production checkout is available. The calibration adapter only needs encoded
// image bytes; the dimensions are carried for clients that already know them.
// Keep this file in sync with the production contract before deployment.

#ifndef PHYTOCOMMON_ICE
#define PHYTOCOMMON_ICE

#include "CommonPhenoseeder.ice"

module Phyto
{
    module Common
    {
        sequence<byte> ByteSeq;

        struct imageData
        {
            ByteSeq data;
            int width;
            int height;
            int channels;
        };

        struct intrinsicParams
        {
            // Row-major 3x3 intrinsic matrix.
            CommonPhenoseeder::vecOfDoubles matrix;
        };

        struct extrinsicParams
        {
            CommonPhenoseeder::vecOfDoubles rotation;
            CommonPhenoseeder::vecOfDoubles translation;
        };
    };
};

#endif
