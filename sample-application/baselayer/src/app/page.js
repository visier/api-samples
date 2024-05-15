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
import ExpenseReport from './data-query-objects/page';
import DataIntake from './data-intake/page';
import DataQuery from './data-query-metrics/page';
import DataModel from './data-model/page';

import Button from 'react-bootstrap/Button';
import Card from 'react-bootstrap/Card';
import { useRouter } from 'next/navigation';
import 'bootstrap/dist/css/bootstrap.min.css';
import useCredsStore from '@/store/credsStore';
import { Alert } from 'react-bootstrap';
import React from 'react';
import Container from 'react-bootstrap/Container';
import Row from 'react-bootstrap/Row';
import Col from 'react-bootstrap/Col';

export default function Home() {
  const router = useRouter()
  const isAuthenticated = useCredsStore(s => s.isAuthenticated);

  return (
    <>
      {isAuthenticated() ? (
        <Container>
          <Row className="mb-4">
            <Col className="mb-4" sm={6}>
              <h2 style={{ "padding": "40px 20px 10px 20px" }}>Visier Baselayer Application</h2>
              <h4 style={{ "padding": "10px 20px 0 20px" }}>A sample application built on Alpine by Visier</h4>
              <p style={{ "padding": "20px" }}>
                This is a sample Next.js application that shows calls to Visier's Data Model, Data Query, and Data Intake APIs. It utilizes Visier's OAuth 2.0 authentication flow.
                For more information about configuring Visier access with OAuth 2.0, see the README.md. 
              </p>
            </Col>
            <Col sm={6}>
              <h2 style={{ "padding": "40px 20px 10px 20px" }}>Prerequisites</h2>
              <p style={{ "padding": "20px" }}>
                Before calling this application's APIs, you need:
                <ul>
                  <li>A Visier tenant. If you don't already have a Visier tenant, sign up for the <a href="https://www.visier.com/sandbox/">Visier free trial</a>.</li>
                  <li>A registered <a href="https://docs.visier.com/developer/Studio/sign-in%20settings/oauth2.htm">OAuth 2.0</a> client in Visier.</li>
                  <li>A Visier <a href="https://docs.visier.com/developer/Studio/solution%20settings/api-key-generate.htm">API key</a>.</li>
                  <li><a href="https://docs.visier.com/developer/Tutorials/analytic-model/extend-analytic-model-subject.htm">Expense Report objects and loaded data</a> in Visier.</li>
                </ul>
              </p>
            </Col>
          </Row>
          <Row>
            <Col sm={6}>
              <ExpenseReport />
            </Col>
            <Col sm={6}>
              <DataQuery />
            </Col>
          </Row>
          <Row>
            <Col sm={6}>
              <DataModel />
            </Col>
            <Col sm={6}>
              <DataIntake />
            </Col>
          </Row>
        </Container>
      ) : (
        <>
          <Card style={{ width: '40rem' }}>
            <Card.Body>
              <Card.Title>Visier Baselayer Application</Card.Title>
              <Card.Text>
                This is a sample Next.js application that shows the three-legged (`authorization_code` grant type) OAuth authentication with calls to Visier's Data Model, Data Query, and Data Intake APIs.
                For more information about configuring Visier access with OAuth 2.0, see the README.md. 
              </Card.Text>
              <Alert key="warning" variant="warning">
                <b>Note:</b> This sample application shows Visier's public APIs and OAuth 2.0 functionality. For information about acceptable use, see the LICENSE file.
              </Alert>
              <Button variant="primary" onClick={() => router.push("/oauth2/login")}>Login to Visier</Button>
            </Card.Body>
          </Card>
        </>
      )
      }
    </>
  );
}
