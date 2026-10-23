// SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
// SPDX-License-Identifier: Apache-2.0
//
// Local compatibility definition used until the shared CommonPhenoseeder.ice
// from the production checkout is available. Keep this file in sync with that
// contract before deploying a server that must interoperate with other clients.

#ifndef COMMONPHENOSEEDER_ICE
#define COMMONPHENOSEEDER_ICE

module CommonPhenoseeder
{
    sequence<double> vecOfDoubles;
};

#endif
