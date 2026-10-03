import { useState } from "react";
import { CreditCard, Lock, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Link } from "react-router-dom";

function formatCardNumber(v: string) {
    return v.replace(/\D/g, "").slice(0, 16).replace(/(.{4})/g, "$1 ").trim();
}
function formatExpiry(v: string) {
    const digits = v.replace(/\D/g, "").slice(0, 4);
    if (digits.length >= 3) return `${digits.slice(0, 2)}/${digits.slice(2)}`;
    return digits;
}

export default function CreditPay() {
    const [cardNumber, setCardNumber] = useState("");
    const [cardHolder, setCardHolder] = useState("");
    const [expiry, setExpiry] = useState("");
    const [cvv, setCvv] = useState("");
    const [loading, setLoading] = useState(false);
    const [success, setSuccess] = useState(false);
    const [errors, setErrors] = useState<Record<string, string>>({});

    const validate = () => {
        const e: Record<string, string> = {};
        if (cardNumber.replace(/\s/g, "").length < 16) e.cardNumber = "Enter a valid 16-digit card number";
        if (!cardHolder.trim()) e.cardHolder = "Cardholder name is required";
        const [m, y] = expiry.split("/");
        const now = new Date();
        const expMonth = parseInt(m ?? "0");
        const expYear = parseInt("20" + (y ?? "0"));
        if (!m || !y || expMonth < 1 || expMonth > 12 || expYear < now.getFullYear() ||
            (expYear === now.getFullYear() && expMonth < now.getMonth() + 1)) {
            e.expiry = "Invalid or expired date";
        }
        if (cvv.replace(/\D/g, "").length < 3) e.cvv = "CVV must be 3–4 digits";
        return e;
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        const errs = validate();
        setErrors(errs);
        if (Object.keys(errs).length > 0) return;
        setLoading(true);
        await new Promise((r) => setTimeout(r, 1200));
        setLoading(false);
        setSuccess(true);
    };

    if (success) {
        return (
            <div className="flex flex-col items-center justify-center min-h-[60vh] px-4 text-center">
                <CheckCircle2 className="h-16 w-16 text-emerald-500 mb-4" />
                <h2 className="text-2xl font-bold mb-2">Demo complete</h2>
                <p className="text-muted-foreground mb-6">
                    The form validated. No payment was taken and no subscription
                    exists &mdash; this page is a demonstration.
                </p>
                <Button asChild className="rounded-full">
                    <Link to="/">Back to home</Link>
                </Button>
            </div>
        );
    }

    return (
        <div className="max-w-md mx-auto px-4 py-10">
            <div className="flex items-center gap-2 mb-4">
                <CreditCard className="h-6 w-6" />
                <h1 className="text-2xl font-bold">Payment</h1>
            </div>

            {/* This form processes nothing. It exists to demonstrate the
                validation and formatting, so it says so before anyone types
                a real card into it. */}
            <div
                role="note"
                className="mb-6 rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm"
            >
                <p className="font-semibold">Demo form</p>
                <p className="text-muted-foreground mt-0.5">
                    No payment is taken and nothing is sent anywhere &mdash; there is
                    no payment provider behind this page. Use the test number
                    4242&nbsp;4242&nbsp;4242&nbsp;4242 rather than a real card.
                </p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                    <Label htmlFor="cardNumber">Card number</Label>
                    <Input
                        id="cardNumber"
                        placeholder="4242 4242 4242 4242"
                        autoComplete="off"
                        value={cardNumber}
                        onChange={(e) => setCardNumber(formatCardNumber(e.target.value))}
                        inputMode="numeric"
                        className="mt-1"
                    />
                    {errors.cardNumber && <p className="text-xs text-red-500 mt-1">{errors.cardNumber}</p>}
                </div>

                <div>
                    <Label htmlFor="cardHolder">Cardholder name</Label>
                    <Input
                        id="cardHolder"
                        placeholder="John Doe"
                        autoComplete="off"
                        value={cardHolder}
                        onChange={(e) => setCardHolder(e.target.value)}
                        className="mt-1"
                    />
                    {errors.cardHolder && <p className="text-xs text-red-500 mt-1">{errors.cardHolder}</p>}
                </div>

                <div className="grid grid-cols-2 gap-4">
                    <div>
                        <Label htmlFor="expiry">Expiry</Label>
                        <Input
                            id="expiry"
                            placeholder="MM/YY"
                            autoComplete="off"
                            value={expiry}
                            onChange={(e) => setExpiry(formatExpiry(e.target.value))}
                            inputMode="numeric"
                            className="mt-1"
                        />
                        {errors.expiry && <p className="text-xs text-red-500 mt-1">{errors.expiry}</p>}
                    </div>
                    <div>
                        <Label htmlFor="cvv">CVV</Label>
                        <Input
                            id="cvv"
                            placeholder="123"
                            autoComplete="off"
                            value={cvv}
                            onChange={(e) => setCvv(e.target.value.replace(/\D/g, "").slice(0, 4))}
                            inputMode="numeric"
                            className="mt-1"
                        />
                        {errors.cvv && <p className="text-xs text-red-500 mt-1">{errors.cvv}</p>}
                    </div>
                </div>

                <div className="flex items-center gap-1.5 text-xs text-muted-foreground mt-2">
                    <Lock className="h-3 w-3" />
                    Nothing entered here leaves the page.
                </div>

                <Button type="submit" className="w-full" disabled={loading}>
                    {loading ? "Processing…" : "Pay now"}
                </Button>
            </form>
        </div>
    );
}
