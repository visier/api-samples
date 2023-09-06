#!/bin/bash

# Copyright 2023 Visier Solutions Inc.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

source ./authenticate.sh

apikey=$VISIER_APIKEY
vhost=$VISIER_HOST

access_token=$(echo $JWT | jq -r '.access_token')
token_type=$(echo $JWT | jq -r '.token_type')

curl -s -X GET \
    "$vhost/v1/data/model/analytic-objects/Employee/dimensions/Gender/members" \
    -H "apikey:$apikey" \
    -H "Authorization: $token_type $access_token"