"use client"
import { useState } from "react";
import SelectEmployee from "./select-employee";
import DisplayEmployee from "./display-emplyee";

export default function Employee() {
    const [selectedEmp, setSelectedEmp] = useState();

    return (
        <>
            <SelectEmployee setEmp={setSelectedEmp}></SelectEmployee>
            <DisplayEmployee empId={selectedEmp}></DisplayEmployee>
        </>
    )
}