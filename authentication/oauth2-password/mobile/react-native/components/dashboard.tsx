import React, { useContext } from 'react';
import { View, Text } from 'react-native';
import { AuthContext } from '../contexts/authcontext';

const Dashboard: React.FC = () => {

    const { accessToken, setAccessToken } = useContext(AuthContext);

    return (
        <View>
            <Text>{accessToken}</Text>
            {/* Add your dashboard components and content here */}
        </View>
    );
};

export default Dashboard;