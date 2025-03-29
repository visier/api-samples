// Copyright 2023 Visier Solutions Inc.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

"use client"
import React, { useState } from "react";
import Card from 'react-bootstrap/Card';
import Button from 'react-bootstrap/Button';
import Table from 'react-bootstrap/Table';

import Form from 'react-bootstrap/Form';
import useCredsStore from "@/store/credsStore";

export default function DataQuery() {
  const [expenseReportsValue, setExpenseReportsValue] = useState(null);
  const [expenseReportsCount, setExpenseReportsCount] = useState(null);

  const [authHeader, config] = useCredsStore(s => [s.authHeader, s.config]);

  const handleCall = async () => {
    const expensiveReportsValueRequestBody = {
      auth: authHeader(),
      config: {
        ...config,
        headers: {
          ...config.headers,
          'Content-Type': 'application/json',
          'Accept': 'text/csv'
        }
      },
      query: "SELECT Expense_Reports_Value() AS Sum FROM Expense_Report",
      url: encodeURI("/v1/data/query/sql"),
      method: "POST"
    };

    fetch("/api/execute", {
      method: "POST",
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(expensiveReportsValueRequestBody)
    }).then(response => response.json())
      .then(data => {
        const lines = data.split('\r\n');
        const [count, visierTime] = lines[1].split(',');

        const formattedData = {
          count: count.trim(),
          visierTime: visierTime.trim().split(' - ')[0] // Extract the datetime without ' - [0]'.
        };

        setExpenseReportsValue(formattedData);
      });

    const expensiveReportsCountRequestBody = {
      auth: authHeader(),
      config: {
        ...config,
        headers: {
          ...config.headers,
          'Content-Type': 'application/json',
          'Accept': 'text/csv'
        }
      },
      query: "SELECT Expense_Reports_Count() AS Count FROM Expense_Report",
      url: encodeURI("/v1/data/query/sql"),
      method: "POST"
    };

    fetch("/api/execute", {
      method: "POST",
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(expensiveReportsCountRequestBody)
    }).then(response => response.json())
      .then(data => {
        const lines = data.split('\r\n');
        const [count, visierTime] = lines[1].split(',');

        const formattedData = {
          count: count.trim(),
          visierTime: visierTime.trim().split(' - ')[0] // Extract the datetime without ' - [0]'.
        };

        setExpenseReportsCount(formattedData);
      });
  };


  return (
    <Card style={{ width: '100%' }} className="m-3">
      <Card.Body>
        <Card.Title>Aggregate Data Metric Retrieval (Data Query API - SQL)</Card.Title>
        <Card.Text>
          The Data Model and Data Query APIs provide you with the ability to discover and inspect the data model objects within your solution and perform aggregation and list queries to retrieve data from Visier. Let's send our first request to retrieve the list of all metrics.
        </Card.Text>
        <Form>
          <Form.Group controlId="apiTransaction">
            <Button variant="primary" onClick={handleCall}>Call Aggregate Metrics API</Button>
          </Form.Group>
          <Table striped bordered hover>
            <thead>
              <tr>
                <th colspan="2">Expense Report Data Query</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Date</td>
                <td>{expenseReportsCount?.visierTime}</td>
              </tr>
              <tr>
                <td>Count of Expense Reports</td>
                <td>{expenseReportsCount?.count}</td>
              </tr>
              <tr>
                <td>Value of Expense Reports</td>
                <td>{expenseReportsValue?.count}</td>
              </tr>
              <tr>
                <td>Average Value of Expense Report</td>
                <td>{expenseReportsValue?.count / expenseReportsCount?.count}</td>
              </tr>
            </tbody>
          </Table>
        </Form>
      </Card.Body>
    </Card>
  );
}
