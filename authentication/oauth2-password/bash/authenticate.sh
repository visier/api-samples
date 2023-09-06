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

# Assign local variables
apikey=$VISIER_APIKEY
vhost=$VISIER_HOST
client_id=$VISIER_CLIENT_ID
client_secret=$VISIER_CLIENT_SECRET
vuser=$VISIER_USERNAME
vpassword=$VISIER_PASSWORD
grant_type="password"

# Compose request body and request token from password grant
body="grant_type=$grant_type&client_id=$client_id&scope=read&username=$vuser&password=$vpassword"
JWT=$(curl -s -X POST \
        "$vhost/v1/auth/oauth2/token" \
        -H "apikey: $apikey" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d $body \
        -u "$client_id:$client_secret")
export JWT
