#!/bin/bash

source ./authenticate.sh

apikey=$VISIER_APIKEY
vhost=$VISIER_HOST

access_token=$(echo $JWT | jq -r '.access_token')
token_type=$(echo $JWT | jq -r '.token_type')

curl -s -X GET \
    "$vhost/v1/data/model/analytic-objects/Employee/dimensions/Gender/members" \
    -H "apikey:$apikey" \
    -H "Authorization: $token_type $access_token"