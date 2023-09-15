export default function POST(request) {
    // TODO: request body validation
    const requestBody = request.body;
    console.log(requestBody, request);

    return new Response({message: "nothing yet"}, {status: 200});
}