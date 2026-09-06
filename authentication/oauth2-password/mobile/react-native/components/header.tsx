import React from 'react';
import { Text, View, StyleSheet } from 'react-native';

type CustomHeaderProps = {
  title: string;
};

const CustomHeader: React.FC<CustomHeaderProps> = ({ title }) => {
  return (
    <View style={styles.headerContainer}>
      <Text style={styles.headerTitle}>{title}</Text>
    </View>
  );
};

const styles = StyleSheet.create({
  headerContainer: {
    marginTop: 32,
    paddingHorizontal: 24,
    backgroundColor: '#f5f5f5',
    padding: 10,
  },
  headerTitle: {
    fontSize: 24,
    fontWeight: '600',
  },
});

export default CustomHeader;