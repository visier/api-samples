// pages/api/execute.js

import { POST } from '../../src/app/execute/route';

export default async (req, res) => {
  if (req.method === 'POST') {
    // Check if request method is POST
    try {
      const data = await POST(req);
      res.status(200).json(data.data);
    } catch (error) {
      res.status(500).json({ error: error.toString() }); // Make sure your error is serializable or use error.message
    }
  } else {
    // Handle any requests that aren't POST
    res.status(405).json({ error: 'Method not allowed' });
  }
}
