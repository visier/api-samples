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

export default function SelectExpense({ setSelectedReportId }) {
  const [expenseReports, setExpenseReports] = useState([]);
  const [authHeader, config] = useCredsStore(s => [s.authHeader, s.config]);

  const setReports = async response => {
    const payload = await response.json()
    if (payload.rows !== undefined && payload.rows.length > 0) {
      const first50Rows = payload.rows.slice(0, 50); // Take the first 50 rows so it isn't too large.
      const expenseReports = first50Rows.map((r, index) => ({
        key: r['0'],
        name: r['0']
      }));
      setExpenseReports(expenseReports);
    } else {
      setExpenseReports([]);
    }
  }

  const expenseFetchError = error => {
    console.log(error);
    console.error("Unable to fetch expense reports", error);
  }

  const fetchExpenses = e => {
    const requestBody = {
      auth: authHeader(),
      config: {
        ...config,
        headers: {
          ...config.headers,
          'Content-Type': 'application/json',
        }
      },
      query: "SELECT Expense_Report.Expense_ReportID FROM Expense_Report",
      url: encodeURI("/v1/data/query/sql"),
      method: "POST"
    };

    fetch("/api/execute", {
      method: "POST",
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody)
    }).then(setReports).catch(expenseFetchError)
  }
  const renderExpenseReports = () => {
    if (expenseReports.length === 0) {
      return (<option key="-1" value="-1" disabled>No expense reports available.</option>)
    } else {
      return expenseReports.map(rec => (<option key={rec.key} value={rec.key}>{rec.name}</option>))
    }
  }

  const expenseReportSelected = e => {
    const expenseId = e.target.value;
    setSelectedReportId(expenseId);
  }

  useEffect(() => {
    fetchExpenses({ target: { value: "" } });
  }, []);

  return (
    <Form>
      <Form.Group className="mb-3" controlId="exampleForm.ControlTextarea1">
        <Form.Label>{expenseReports.length} Expense Reports</Form.Label>
        <Form.Select aria-label="Default select example" htmlSize="8" onChange={expenseReportSelected}>
          {renderExpenseReports()}
        </Form.Select>
      </Form.Group>
    </Form>
  )
}
