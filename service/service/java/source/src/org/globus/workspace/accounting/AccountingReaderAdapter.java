/*
 * Copyright 1999-2008 University of Chicago
 *
 * Licensed under the Apache License, Version 2.0 (the "License"); you may not
 * use this file except in compliance with the License. You may obtain a copy
 * of the License at
 *
 *    http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
 * WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
 * License for the specific language governing permissions and limitations
 * under the License.
 */

package org.globus.workspace.accounting;

import org.globus.workspace.WorkspaceException;

public interface AccountingReaderAdapter extends AccountingAdapter {

    public long totalElapsedMinutes(String ownerDN) throws WorkspaceException;

    public long currentReservedMinutes(String ownerDN)
            throws WorkspaceException;

    public long totalElapsedAndReservedMinutes(String ownerDN)
            throws WorkspaceException;

    public ElapsedAndReservedMinutes
                totalElapsedAndReservedMinutesTuple(String ownerDN)
            throws WorkspaceException;

    // Any portion used costs this many minutes (ceiling).
    // If this is for example set to 60, then 1 minute will cost 60 minutes,
    // 61 minutes will cost 120, etc.
    public int getChargeGranularity();
}
