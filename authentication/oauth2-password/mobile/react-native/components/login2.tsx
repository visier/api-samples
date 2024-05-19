import React, { useState } from 'react';
import { View, StyleSheet } from 'react-native';
import { Button, TextInput } from 'react-native-paper';
import axios from "axios";

const apikey = "INSERT-YOUR-API-KEY";
const vhost = "INSERT-YOUR-API-URL";
const grantType = "urn:visier:params:oauth:grant-type:asid-token";

function Login2() {
  const [username, setUsername] = useState('EMAILADDRESS');
  const [password, setPassword] = useState('PASSWORD');

  const authenticate = async (instance: any) => {
    const url = "/v1/admin/visierSecureToken"
    const body = {
        grant_type: grantType,
        scope: "read",
        username,
        password
    }
    const config = {
        headers: {
            "Content-Type": "application/x-www-form-urlencoded"
        },
    }
    return instance.post(url, body, config).then((response: { data: any; }) => {
        const jwt = response.data
        const tokenType = jwt.token_type
        const accessToken = jwt.access_token

        // Request interceptor without retry logic.
        instance.interceptors.request.use((config: { headers: { Authorization: string; }; }) => {
            config.headers.Authorization = `${tokenType} ${accessToken}`
            return config
        })
        return jwt
    }).catch((error: any) => {
        // console.log(error)
                console.log(error); // Log the error object
        if (error.response) {
          // The request was made and the server responded with a status code
          // that falls out of the range of 2xx
          console.log(error.response.data);
          console.log(error.response.status);
          console.log(error.response.headers);
        } else if (error.request) {
          // The request was made but no response was received
          console.log(error.request);
        } else {
          // Something happened in setting up the request that triggered an Error
          console.log('Error', error.message);
        }
        console.log(error.config);
    })

}


  const handleLogin = async () => {
    // Handle login logic here
    try {
        const instance = axios.create({
            baseURL: vhost,
            headers: {
                apikey: apikey
            }
        })

    
        const r = await authenticate(instance)
        // const r = await sampleApiCall(instance)
        console.log(r)
    } catch (err) {
        console.error("Unable to call Visier API with password grant authentication. Details: " + err)
    }
  };

  return (
    <View style={styles.container}>
      <TextInput
        label="Username"
        value={username}
        onChangeText={setUsername}
        mode="outlined"
        style={styles.input}
      />
      <TextInput
        label="Password"
        value={password}
        onChangeText={setPassword}
        secureTextEntry={true}
        mode="outlined"
        style={styles.input}
      />
      <Button mode="contained" onPress={handleLogin} style={styles.button}>
        Login
      </Button>
    </View>
  );
}

const styles = StyleSheet.create({
    container: {
      flex: 1,
      justifyContent: 'center',
      padding: 16,
    },
    input: {
      height: 50,
      marginBottom: 12,
      backgroundColor: '#fff',
    },
    button: {
      marginTop: 12,
    },
  });
  

export default Login2;