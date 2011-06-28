/*
 * Copyright 1999-2010 University of Chicago
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
package org.globus.workspace.remoting.admin;

public class VMTranslation {

    private String id;
    private String node;
    private String groupId;
    private String callerIdentity;
    private String state;
    private String startTime;
    private String endTime;
    private String memory;
    private String cpuCount;

    public VMTranslation() {}

    public VMTranslation(String id, String node, String groupId, String callerIdentity, String state,
                            String startTime, String endTime, String memory, String cpuCount) {
        this.id = id;
        this.node = node;
        this.groupId = groupId;
        this.callerIdentity = callerIdentity;
        this.state = state;
        this.startTime = startTime;
        this.endTime = endTime;
        this.memory = memory;
        this.cpuCount = cpuCount;
    }

    public String getId() {
        return id;
    }
    public String getNode() {
        return node;
    }
    public String getGroupId() {
        return groupId;
    }
    public String getCallerIdentity() {
        return callerIdentity;
    }
    public String getState() {
        return state;
    }
    public String getStartTime() {
        return startTime;
    }
    public String getEndTime() {
        return endTime;
    }
    public String getMemory() {
        return memory;
    }
    public String getCpuCount() {
        return cpuCount;
    }
}
