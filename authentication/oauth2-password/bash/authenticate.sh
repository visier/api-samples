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
        -H "apikey:$apikey" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d $body \
        -u "$client_id:$client_secret")
export JWT
