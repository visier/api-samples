import { useState } from "react";
import { Form } from "react-bootstrap";

export default function SelectEmployee({ setEmp }) {
    const [empFilter, setEmpFilter] = useState();
    const [empRecords, setEmpRecords] = useState([]);
    
    const fetchEmployees = filter => {

    }

    const renderEmployees = () => {
        if (empRecords.length === 0) {
            return (<option value="-1" disabled>No employees found. Enter a filter with at least 3 characters.</option>)
        } else {
            return empRecords.map(rec => (<option value={rec.id}>rec.name</option>))
        }
    }
    return (
        <Form>
            <Form.Group className="mb-3" controlId="exampleForm.ControlInput1">
                <Form.Label>Full name filter</Form.Label>
                <Form.Control type="text"
                    placeholder="Start typing in the name of the employee..." 
                    onInput={e => fetchEmployees(e.target.value)}/>
            </Form.Group>
            <Form.Group className="mb-3" controlId="exampleForm.ControlTextarea1">
                <Form.Label>Matching Employees</Form.Label>
                <Form.Select aria-label="Default select example" htmlSize="8">
                    {renderEmployees()}
                </Form.Select>
            </Form.Group>
        </Form>
        )
    }
    