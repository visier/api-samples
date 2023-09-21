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

import { Table } from "react-bootstrap";
import React from "react";

export default function DisplayProperties({ details }) {
    const makeRows = () => {
        return details.map( prop => {
            return (<tr key={prop.name}>
                <td>{prop.name}</td>
                <td>{prop.value}</td>
            </tr>)
        })
    }

    return (
        <Table striped bordered>
        <thead>
            <tr>
                <th>Property</th>
                <th>Value</th>
            </tr>
        </thead>
        <tbody>
            {makeRows()}
        </tbody>
    </Table>
    )
}