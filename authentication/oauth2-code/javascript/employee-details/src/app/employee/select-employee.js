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

import React, { useState, useEffect } from "react";
import { Form } from "react-bootstrap";
import useCredsStore from "@/store/credsStore";

export default function SelectEmployee({ setSelectedEmpId }) {
    const [empRecords, setEmpRecords] = useState([]);
    const [authHeader, config] = useCredsStore(s => [s.authHeader, s.config]);
    
    const setEmployees = async response => {
        const payload = await response.json()
        if (payload.members !== undefined && payload.members.length > 0) {
            const employeeRecords = payload.members.map(m => ({
                key: m.path[0],
                name: m.displayName
            }));

            setEmpRecords(employeeRecords);
        } else {
            setEmpRecords([]);
        }
    }

    const employeeFetchError = error => {
        console.error("Unable to fetch Employees", error);
    }

    const fetchEmployees = e => {
        const filter = encodeURIComponent(e.target.value);
        const filterArgs = filter.length > 0 ? `&field=either&filter=.*${filter}.*` : "";
        const requestBody = {
            auth: authHeader(),
            config,
            url: `/v1/data/model/analytic-objects/Employee/dimensions/EmployeeID_Hierarchy/members?limit=50${filterArgs}`,
            method: "GET"
        }

        fetch("/execute", {
            method: "POST",
            body: JSON.stringify(requestBody)
        }).then(setEmployees).catch(employeeFetchError)
    }

    const renderEmployees = () => {
        if (empRecords.length === 0) {
            return (<option key="-1" value="-1" disabled>No employees available or matching the filter.</option>)
        } else {
            return empRecords.map(rec => (<option key={rec.key} value={rec.key}>{rec.name}</option>))
        }
    }

    const employeeSelected = e => {
        const employeeId = e.target.value;
        setSelectedEmpId(employeeId);
    }
    
    useEffect(() => {
        fetchEmployees({ target: { value: "" }});
    }, []);

    return (
        <Form>
            <Form.Group className="mb-3" controlId="exampleForm.ControlInput1">
                <Form.Label>Full name filter</Form.Label>
                <Form.Control type="text"
                    placeholder="Start typing in the name of the employee. Filter is case-sensitive. Results are capped at 50 items." 
                    onInput={fetchEmployees}/>
            </Form.Group>
            <Form.Group className="mb-3" controlId="exampleForm.ControlTextarea1">
                <Form.Label>{empRecords.length} Matching Employees</Form.Label>
                <Form.Select aria-label="Default select example" htmlSize="8" onChange={employeeSelected}>
                    {renderEmployees()}
                </Form.Select>
            </Form.Group>
        </Form>
        )
    }
    