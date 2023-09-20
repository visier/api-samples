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
import { ErrorBoundary } from "react-error-boundary";
import SelectEmployee from "./select-employee";
import DisplayEmployee from "./display-employee";
import Error from "./error";
import { Card } from "react-bootstrap";

export default function Employee() {
    const [selectedEmpId, setSelectedEmpId] = useState();

    return (
        <Card style={{ width: '60rem'}}>
            <ErrorBoundary fallback={<Error />}>
                <SelectEmployee setSelectedEmpId={setSelectedEmpId}></SelectEmployee>
                <DisplayEmployee selectedEmpId={selectedEmpId}></DisplayEmployee>
            </ErrorBoundary>
        </Card>
    )
}