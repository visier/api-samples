/**
 * Sample React Native App using API from https://developer.visier.com/
 */

import React, {useState} from 'react';
import type {PropsWithChildren} from 'react';
import {
  SafeAreaView,
  ScrollView,
  StatusBar,
  StyleSheet,
  Text,
  useColorScheme,
  View,
} from 'react-native';

import {
  Colors,
  DebugInstructions,
  Header,
  LearnMoreLinks,
  ReloadInstructions,
} from 'react-native/Libraries/NewAppScreen';
import LoginWithOAuth2 from './components/loginWithOAuth2';
import CustomHeader from './components/header';
import {createStackNavigator} from '@react-navigation/stack';
import {NavigationContainer} from '@react-navigation/native';
import Dashboard from './components/dashboard';
import {AuthContext} from './contexts/authcontext';
import LoginWithVisierSecureToken from './components/loginWithVisierSecureToken';

type SectionProps = PropsWithChildren<{
  title: string;
}>;

const Stack = createStackNavigator();

function App(): React.JSX.Element {
  const isDarkMode = useColorScheme() === 'dark';
  const [accessToken, setAccessToken] = useState<string | null>(null);

  const backgroundStyle = {
    backgroundColor: isDarkMode ? Colors.darker : Colors.lighter,
  };

  return (
    <AuthContext.Provider value={{accessToken, setAccessToken}}>
      <NavigationContainer>
        <Stack.Navigator initialRouteName="Login">
          <Stack.Screen name="Login" component={LoginWithOAuth2} />
          {/* 
          // Alternatively you can auth with VisierSecureToken instead if you use LoginWithVisierSecureToken
          <Stack.Screen name="Login" component={LoginWithVisierSecureToken} /> 
          */}
          <Stack.Screen name="Dashboard" component={Dashboard} />
        </Stack.Navigator>
      </NavigationContainer>
    </AuthContext.Provider>
  );
}

const styles = StyleSheet.create({
  sectionContainer: {
    marginTop: 32,
    paddingHorizontal: 24,
  },
  sectionTitle: {
    fontSize: 24,
    fontWeight: '600',
  },
  sectionDescription: {
    marginTop: 8,
    fontSize: 18,
    fontWeight: '400',
  },
  highlight: {
    fontWeight: '700',
  },
});

export default App;
