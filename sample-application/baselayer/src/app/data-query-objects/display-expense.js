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

export default function DisplayExpense({ selectedReportId }) {
  const [expDetails, setExpDetails] = useState([]);
  const [authHeader, config] = useCredsStore(s => [s.authHeader, s.config]);

  const fetchDetails = () => {
    const requestBody = {
      auth: authHeader(),
      config,
      url: encodeURI("/v1/data/query/sql"),
      method: "POST",
      query: `SELECT Expense_Report.Amount_Due, Expense_Report.Currency_Code, Expense_Report.Date_Created, Expense_Report.Total_Claimed_Amount FROM Expense_Report WHERE Expense_Report.Expense_ReportID = '${selectedReportId}' AND ${dateRangeFilter()}`
    }

    fetch("/api/execute", {
      method: "POST",
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody)
    }).then(setExpenseDetails)
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

  const setExpenseDetails = async responsePromise => {
    const response = await responsePromise.json();
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
      setExpDetails(details);
    } else {
      setExpDetails([]);
    }
  }

  const displayIfPossible = () => {
    if (selectedReportId === undefined) {
      return (<p>Select an expense report to inspect it.</p>)
    } else if (selectedReportId.length === 0) {
      return (
        <Alert key="primary" variant="primary" dismissible>
          {selectedReportId} does not have any recent activity.
        </Alert>)
    } else {
      return (<DisplayProperties details={expDetails} />)
    }
  }

  useEffect(() => {
    fetchDetails();
  }, [selectedReportId]);

  return (displayIfPossible())
}