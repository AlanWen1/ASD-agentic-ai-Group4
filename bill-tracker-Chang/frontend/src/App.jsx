import { useEffect, useState } from "react";

const API = "http://localhost:5004/api";


const emptyBill = {
    name: "",
    amount: "",
    due_date: "",
    frequency: "monthly",
    status: "pending"
};


function App() {

    const [bills, setBills] = useState([]);
    const [bill, setBill] = useState(emptyBill);
    const [editingId, setEditingId] = useState(null);

    const [chatInput, setChatInput] = useState("");
    const [chatMessages, setChatMessages] = useState([]);

    const [loading, setLoading] = useState(false);
    const [chatLoading, setChatLoading] = useState(false);


    useEffect(() => {
        loadBills();
    }, []);


    async function loadBills() {

        setLoading(true);

        try {

            const response = await fetch(
                `${API}/bills`
            );

            const data = await response.json();

            setBills(data);

        } catch (error) {

            console.error(error);

        } finally {

            setLoading(false);

        }
    }


    function handleChange(event) {

        const {
            name,
            value
        } = event.target;

        setBill({
            ...bill,
            [name]: value
        });
    }


    async function saveBill(event) {

        event.preventDefault();

        const method = editingId
            ? "PUT"
            : "POST";

        const url = editingId
            ? `${API}/bills/${editingId}`
            : `${API}/bills`;

        await fetch(url, {

            method,

            headers: {
                "Content-Type": "application/json"
            },

            body: JSON.stringify({
                ...bill,
                amount: Number(bill.amount)
            })
        });

        setBill(emptyBill);
        setEditingId(null);

        await loadBills();
    }


    function editBill(item) {

        setEditingId(item.id);

        setBill({
            name: item.name,
            amount: item.amount,
            due_date: item.due_date,
            frequency: item.frequency,
            status: item.status
        });
    }


    async function deleteBill(id) {

        if (!window.confirm(
            "Delete this bill?"
        )) {
            return;
        }

        await fetch(
            `${API}/bills/${id}`,
            {
                method: "DELETE"
            }
        );

        await loadBills();
    }


    async function sendChat(event) {

        event.preventDefault();

        if (!chatInput.trim()) {
            return;
        }

        const question = chatInput;

        setChatInput("");

        setChatMessages(messages => [
            ...messages,
            {
                role: "user",
                content: question
            }
        ]);

        setChatLoading(true);

        try {

            const response = await fetch(
                `${API}/chat`,
                {
                    method: "POST",

                    headers: {
                        "Content-Type": "application/json"
                    },

                    body: JSON.stringify({
                        message: question
                    })
                }
            );

            const data = await response.json();

            setChatMessages(messages => [
                ...messages,
                {
                    role: "assistant",
                    content:
                        data.response ||
                        data.error ||
                        "No response."
                }
            ]);

        } catch (error) {

            setChatMessages(messages => [
                ...messages,
                {
                    role: "assistant",
                    content:
                        "Unable to connect to the AI service."
                }
            ]);

        } finally {

            setChatLoading(false);

        }
    }


    const total = bills.reduce(
        (sum, item) =>
            sum + Number(item.amount),
        0
    );


    const unpaid = bills.filter(
        item => item.status !== "paid"
    ).length;


    return (
        <div className="app">

            <header>
                <div>
                    <h1>Bill Tracker</h1>
                    <p>
                        Manage your recurring bills
                    </p>
                </div>
            </header>


            <main>

                <section className="summary">

                    <div className="summary-card">
                        <span>Total Bills</span>
                        <strong>{bills.length}</strong>
                    </div>

                    <div className="summary-card">
                        <span>Total Amount</span>
                        <strong>
                            ${total.toFixed(2)}
                        </strong>
                    </div>

                    <div className="summary-card">
                        <span>Unpaid</span>
                        <strong>{unpaid}</strong>
                    </div>

                </section>


                <div className="content">

                    <section className="panel">

                        <h2>
                            {editingId
                                ? "Edit Bill"
                                : "Add Bill"}
                        </h2>

                        <form
                            onSubmit={saveBill}
                            className="bill-form"
                        >

                            <label>
                                Bill Name
                                <input
                                    name="name"
                                    value={bill.name}
                                    onChange={handleChange}
                                    required
                                />
                            </label>


                            <label>
                                Amount
                                <input
                                    name="amount"
                                    type="number"
                                    min="0"
                                    step="0.01"
                                    value={bill.amount}
                                    onChange={handleChange}
                                    required
                                />
                            </label>


                            <label>
                                Due Date
                                <input
                                    name="due_date"
                                    type="date"
                                    value={bill.due_date}
                                    onChange={handleChange}
                                    required
                                />
                            </label>


                            <label>
                                Frequency
                                <select
                                    name="frequency"
                                    value={bill.frequency}
                                    onChange={handleChange}
                                >
                                    <option value="weekly">
                                        Weekly
                                    </option>

                                    <option value="fortnightly">
                                        Fortnightly
                                    </option>

                                    <option value="monthly">
                                        Monthly
                                    </option>

                                    <option value="quarterly">
                                        Quarterly
                                    </option>

                                    <option value="yearly">
                                        Yearly
                                    </option>

                                    <option value="one-time">
                                        One-time
                                    </option>
                                </select>
                            </label>


                            <label>
                                Status
                                <select
                                    name="status"
                                    value={bill.status}
                                    onChange={handleChange}
                                >
                                    <option value="pending">
                                        Pending
                                    </option>

                                    <option value="paid">
                                        Paid
                                    </option>

                                    <option value="overdue">
                                        Overdue
                                    </option>
                                </select>
                            </label>


                            <div className="form-actions">

                                <button
                                    type="submit"
                                    className="primary"
                                >
                                    {editingId
                                        ? "Update Bill"
                                        : "Add Bill"}
                                </button>

                                {editingId && (
                                    <button
                                        type="button"
                                        onClick={() => {
                                            setEditingId(null);
                                            setBill(emptyBill);
                                        }}
                                    >
                                        Cancel
                                    </button>
                                )}

                            </div>

                        </form>

                    </section>


                    <section className="panel bills-panel">

                        <div className="panel-header">
                            <h2>Your Bills</h2>

                            <button
                                onClick={loadBills}
                            >
                                Refresh
                            </button>
                        </div>


                        {loading ? (
                            <p>Loading bills...</p>
                        ) : bills.length === 0 ? (
                            <p>No bills found.</p>
                        ) : (

                            <div className="table-wrapper">

                                <table>

                                    <thead>
                                        <tr>
                                            <th>Name</th>
                                            <th>Amount</th>
                                            <th>Due Date</th>
                                            <th>Frequency</th>
                                            <th>Status</th>
                                            <th></th>
                                        </tr>
                                    </thead>


                                    <tbody>

                                        {bills.map(item => (

                                            <tr key={item.id}>

                                                <td>
                                                    {item.name}
                                                </td>

                                                <td>
                                                    $
                                                    {Number(
                                                        item.amount
                                                    ).toFixed(2)}
                                                </td>

                                                <td>
                                                    {item.due_date}
                                                </td>

                                                <td>
                                                    {item.frequency}
                                                </td>

                                                <td>
                                                    <span
                                                        className={
                                                            `status ${item.status}`
                                                        }
                                                    >
                                                        {item.status}
                                                    </span>
                                                </td>

                                                <td className="actions">

                                                    <button
                                                        onClick={() =>
                                                            editBill(item)
                                                        }
                                                    >
                                                        Edit
                                                    </button>

                                                    <button
                                                        className="danger"
                                                        onClick={() =>
                                                            deleteBill(item.id)
                                                        }
                                                    >
                                                        Delete
                                                    </button>

                                                </td>

                                            </tr>

                                        ))}

                                    </tbody>

                                </table>

                            </div>

                        )}

                    </section>


                    <section className="panel chat-panel">

                        <h2>AI Bill Assistant</h2>

                        <p className="chat-description">
                            Ask questions about your bills.
                            The AI has access to the current
                            bill data.
                        </p>


                        <div className="chat-messages">

                            {chatMessages.length === 0 && (

                                <div className="chat-empty">
                                    Try asking:
                                    <br />
                                    "What bills are due soon?"
                                    <br />
                                    "How much are my unpaid bills?"
                                </div>

                            )}


                            {chatMessages.map(
                                (message, index) => (

                                    <div
                                        key={index}
                                        className={
                                            `message ${message.role}`
                                        }
                                    >
                                        {message.content}
                                    </div>

                                )
                            )}

                            {chatLoading && (
                                <div className="message assistant">
                                    Thinking...
                                </div>
                            )}

                        </div>


                        <form
                            className="chat-form"
                            onSubmit={sendChat}
                        >

                            <input
                                value={chatInput}
                                onChange={e =>
                                    setChatInput(e.target.value)
                                }
                                placeholder="Ask about your bills..."
                            />

                            <button
                                type="submit"
                                className="primary"
                                disabled={chatLoading}
                            >
                                Send
                            </button>

                        </form>

                    </section>

                </div>

            </main>

        </div>
    );
}


export default App;
