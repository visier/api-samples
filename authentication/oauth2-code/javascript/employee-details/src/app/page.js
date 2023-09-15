"use client"
import Employee from './employee/page';
import { useAuth } from '@/hooks/useAuth';
import Button from 'react-bootstrap/Button';
import Card from 'react-bootstrap/Card';
import { useRouter } from 'next/navigation';
import 'bootstrap/dist/css/bootstrap.min.css';

export default function Home() {
    const { isAuthenticated, accessToken } = useAuth();
    const router = useRouter()
    return (
        <>
            {isAuthenticated() ? <Employee /> : (
                <>
                    <Card style={{ width: '30rem' }}>
                        <Card.Body>
                            <Card.Title>Visier Employee Data Sample</Card.Title>
                            <Card.Text>
                                Sample Next.js application that shows the three-legged (authorization_code flow) OAuth authentication.
                                Instructions for how to set up the environment goes here.
                            </Card.Text>
                            <Button variant="primary" onClick={() => router.push("/oauth2/login")}>Login to Visier</Button>
                        </Card.Body>
                    </Card>
                </>
            )}
        </>
    );
}
