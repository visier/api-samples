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
import React, { useEffect, useState } from "react";
import useCredsStore from "@/store/credsStore";
import { Alert } from "react-bootstrap";
import DisplayProperties from "./display-properties";
import { useShallow } from 'zustand/react/shallow';

export default function DisplayEmployee({ selectedEmpId }) {
    const [empDetails, setEmpDetails] = useState([]);
    const [authHeader, config] = useCredsStore(useShallow(s => [s.authHeader, s.config]));

    const fetchDetails = () => {
    
        const queryBody = {
            query: `SELECT EmployeeId, Full_Name, Gender, Age FROM Employee WHERE EmployeeId = '${selectedEmpId}' AND ${dateRangeFilter()}`
        }
        const requestBody = {
            auth: authHeader(),
            config,
            url: encodeURI("/v1/data/query/sql"),
            method: "POST",
            body: queryBody
        }

        fetch("/execute", {
            method: "POST",
            body: JSON.stringify(requestBody)
        }).then(setEmployeeDetails)
    };

    const dateRangeFilter = () => {
        const dateStr = offset => {
            const d = new Date();
            const roundedByYear = new Date(d.getFullYear() + offset, 1, 1);
            const isoDate = roundedByYear.toISOString().substring(0, 10);
            return `date("${isoDate}")`
        }
        const start = dateStr(-5);
        const end = dateStr(1);
        return `Visier_Time BETWEEN ${start} AND ${end}`;
    }

    const setEmployeeDetails = async responsePromise => {
        const response = await responsePromise.json();
        console.log(response.rows);
        if (response.rows.length > 0) {
            let details = [];
            const single = response.rows[0];
            for (const key of Object.keys(response.header)) {
                const prop = {
                    name: response.header[key],
                    value: single[key]
                }
                details.push(prop);
            }
            setEmpDetails(details);
        } else {
            setEmpDetails([]);

        }
    }

    const displayIfPossible = () => {
        if (selectedEmpId === undefined ) {
            return (<p>Select an employee above.</p>)
        } else if (empDetails.length === 0) {
            return (
            <Alert key="primary" variant="primary" dismissible>
                {selectedEmpId} does not have any recent activity.
            </Alert>)
        } else {
            return (<DisplayProperties details={empDetails} />)
        }
    }

    useEffect(() => {
        fetchDetails();
    }, [selectedEmpId]);

    return (displayIfPossible())
}