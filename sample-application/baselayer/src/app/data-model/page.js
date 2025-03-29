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

export default function DataModel() {
  const [authHeader, config] = useCredsStore(s => [s.authHeader, s.config]);
  const [metricsData, setMetricsData] = useState(null);

  const handleCall = async () => {
    const requestBody = {
      auth: authHeader(),
      config,
      url: encodeURI("/v1/data/model/analytic-objects/Expense_Report"),
      method: "GET"
    };

    fetch("/api/execute", {
      method: "POST",
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody)
    }).then(response => response.json())
      .then(data => {
        setMetricsData(data);
      }).catch(e => {
        console.error('Fetch failed', e);
      });
  };


  return (
    <Card style={{ width: '100%' }} className="m-3">
      <Card.Body>
        <Card.Title>Expense Report Dimensions (Data Model API)</Card.Title>
        <Card.Text>
          The response returns a list of all expense report dimensions.
        </Card.Text>
        <Form>
          <Form.Group controlId="apiTransaction">
            <Button variant="primary" onClick={handleCall}>Call Data Model API</Button>
          </Form.Group>
          <Table striped bordered hover>
            <thead>
              <tr>
                <th colspan="2">Expense Report Data Model</th>
              </tr>
            </thead>
            <tbody>
              {
                metricsData && (
                  <tr>
                    <td>{metricsData.id}</td>
                    <td>
                      <div>
                        <h6>{metricsData.displayName}</h6>
                        <p>{metricsData.description}</p>
                        <p>Data Start Date: {new Date(parseInt(metricsData.dataStartDate)).toLocaleString()}</p>
                        <p>Data End Date: {new Date(parseInt(metricsData.dataEndDate)).toLocaleString()}</p>
                      </div>
                    </td>
                  </tr>
                )
              }
            </tbody>
          </Table>
          <Table striped bordered hover >
            <thead>
              <tr>
                <th>Property IDs</th>
              </tr>
            </thead>
            <tbody>
              {
                metricsData?.propertyIds && metricsData?.propertyIds.map((property, index) => (
                  <tr key={'property-' + index}>
                    <td>{property}</td>
                  </tr>
                ))
              }
            </tbody>
          </Table>
        </Form>
      </Card.Body>
    </Card>
  );
}
