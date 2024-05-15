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
import Form from 'react-bootstrap/Form';
import useCredsStore from "@/store/credsStore";

export default function DataIntake() {
  const [fileName, setFileName] = useState(null);
  const [file, setFile] = useState(null);
  const [transactionId, setTransactionId] = useState(null);
  const [authHeader, config] = useCredsStore(s => [s.authHeader, s.config]);

  const startTransaction = () => {
    const requestBody = {
      auth: authHeader(),
      headers: {
        Cookie: `VisierASIDToken=${authHeader()}`,
      },
      config,
      url: encodeURI("/v1/data/directloads/prod/transactions"),
      method: "POST"
    };

    fetch("/api/execute", {
      method: "POST",
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody)
    }).then(response => response.json())
      .then(data => setTransactionId(data.transactionId));
  };

  const handleChange = (e) => {
    setFile(e.target.files[0]);
    setFileName(e.target.files[0].name);
  };

  const handleUpload = () => {
    if (!file || !transactionId) {
      alert("You must choose a file and specify a transaction ID.");
      return;
    }
    const formData = new FormData();
    formData.append('files', file);
    formData.append('transactionId', transactionId);

    const requestBody = {
      auth: authHeader(),
      config,
      url: encodeURI(`/v1/data/directloads/prod/transactions/${transactionId}/Expense_Report`),
      method: "PUT",
      data: formData,
    };

    fetch("/api/execute", {
      method: "POST",
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody),
    }).then(response => {
      if (response.ok) {
        setUploadStatus("SUCCEEDED");
        alert("File upload succeeded");
      } else {
        setUploadStatus("FAILED");
        alert("File upload failed");
      }
    });
  };

  return (
    <Card style={{ width: '100%' }} className="m-3">
      <Card.Body>
        <Card.Title>Data Upload (Data Intake API)</Card.Title>
        <Card.Text>
          Load data directly into Visier objects. These objects can be delivered as part of Visier Blueprint, locally modified objects, or even completely custom objects.
          Please upload expense report data.
        </Card.Text>
        <Form>
          <Form.Group controlId="apiTransaction">
            <Form.Label>Transaction ID</Form.Label>
            <Form.Control type="text" placeholder="Transaction ID"
              value={transactionId}
              onChange={e => setTransactionId(e.target.value)} />
            <Button variant="primary" onClick={startTransaction}>Start Transaction with API</Button>
          </Form.Group>
          <Form.Group>
            <Form.Control type="file"
              onChange={(event) => {
                setFile(event.target.files[0]);
                setFileName(event.target.files[0]?.name);
              }} />
            <Button variant="primary" onClick={handleUpload}>Upload Data</Button>
            {fileName && (
              <Form.Text className="text-muted">
                {fileName} selected
              </Form.Text>
            )}
          </Form.Group>
        </Form>
      </Card.Body>
    </Card>
  );
}