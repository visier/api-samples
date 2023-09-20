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
import { useEffect } from "react";
import { Alert } from "react-bootstrap";
import React from "react";

export default function Error({ error }) {
    useEffect(() => {
        console.error(error);
    }, [error]);

    return (
        <Alert key="danger" variant="danger" dismissible>
            Unable to fetch employee details. {error}
        </Alert>
    );
}