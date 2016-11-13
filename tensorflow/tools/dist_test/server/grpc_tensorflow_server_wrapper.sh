#!/usr/bin/env bash
# Copyright 2016 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
#
# Wrapper script for grpc_tensorflow_server.py in test server

LOG_FILE="/tmp/grpc_tensorflow_server.log"

SCRIPT_DIR=$( cd ${0%/*} && pwd -P )

# Use the ordinal assigned by the PetSet
# as the task id
TASK_ID=${HOSTNAME##*-}

touch "${LOG_FILE}"

echo Starting GRPC Tensorflow Server with params
echo $@ --task_id=${TASK_ID}
python ${SCRIPT_DIR}/grpc_tensorflow_server.py $@ 2>&1 | tee "${LOG_FILE}"
