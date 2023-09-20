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
import Employee from './employee/page';
import Button from 'react-bootstrap/Button';
import Card from 'react-bootstrap/Card';
import { useRouter } from 'next/navigation';
import 'bootstrap/dist/css/bootstrap.min.css';
import useCredsStore from '@/store/credsStore';
import { Alert } from 'react-bootstrap';
import React from 'react';

export default function Home() {
    const router = useRouter()
    const isAuthenticated = useCredsStore(s => s.isAuthenticated);

    return (
        <>
            {isAuthenticated() ? <Employee /> : (
                <>
                    <Card style={{ width: '40rem'}}>
                        <Card.Body>
                            <Card.Title>Visier Employee Data Sample</Card.Title>
                            <Card.Text>
                                Sample Next.js application that shows the three-legged (authorization_code flow) OAuth authentication. 
                                Please consult the README.md file for how to configure the Visier access using OAuth 2.0.
                            </Card.Text>
                            <Alert key="warning" variant="warning">
                                <b>Note:</b> This is a sample application intended to showcase Visier OAuth authentication. For information about acceptable use, see the LICENSE file.
                            </Alert>
                            <Button variant="primary" onClick={() => router.push("/oauth2/login")}>Login to Visier</Button>
                        </Card.Body>
                    </Card>
                </>
            )}
        </>
    );
}
