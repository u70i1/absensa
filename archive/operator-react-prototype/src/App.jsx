import { useState, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import StudentCard from "./StudentCard/StudentCard";
import InputDevice from "./InputDevice/InputDevice";
import Printer from "./Printer/Printer";
import "./App.css";
import printSound from "./assets/audio/card.wav";
import errorSound from "./assets/audio/printer_error.wav";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

function App() {
  const [student, setStudent] = useState(null);
  const [status, setStatus] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [isSuccess, setIsSuccess] = useState(false);

  const printCardSound = useRef(new Audio(printSound));
  const printerErrorSound = useRef(new Audio(errorSound));

  async function handleScan(nisn) {
    setError(null);
    setIsLoading(true);
    setStudent(null);

    try {
      const response = await fetch(`${API_BASE_URL}/scan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nisn }),
      });

      if (!response.ok) {
        setIsSuccess(false);
        printerErrorSound.current.play();
        const errorData = await response.json();

        switch (response.status) {
          case 404:
            if (errorData.detail?.message === "not_found") {
              setStatus("ERROR: INVALID NISN");
            }
            break;

          case 409:
            if (errorData.detail?.message === "already_exists") {
              setStatus("ERROR: DUPLICATE SCAN");
            }
            break;

          case 500:
            setStatus("ERROR: SERVER ERROR");

          default:
            setStatus(`UNCAUGHT ERROR: ${errorData} (${response.status})`);
            throw new HTTPError(response.status, errorData);
        }
      }

      const data = await response.json();
      setTimeout(() => {
        setStudent(data);
      }, 80);
      setStatus(`SUCCESS: ${data.name} - ${data.nisn}`);
      setIsSuccess(true);
      printCardSound.current.play();
    } catch (err) {
      // setStatus("ERROR: PLEASE TRY AGAIN");
      setError("Failed to scan card. Please try again.");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="app-container">
      <div className="deck-container">
        <div className="deck-wrapper">
          <Printer status={status} isSuccess={isSuccess} />
          <div className="slide">
            <AnimatePresence>
              {student && (
                <motion.div
                  style={{
                    position: "absolute",
                    top: "50%",
                    left: "50%",
                    x: "-50%",
                  }}
                  key={student.nisn}
                  initial={{ y: "-150%", opacity: 1 }}
                  animate={{ y: "-52%", opacity: 1 }}
                  exit={{ y: "100%" }}
                  transition={{ duration: 0.6, ease: [0.23, 1, 0.32, 1] }}
                >
                  <StudentCard
                    name={student.name}
                    nisn={student.nisn}
                    time={student.timestamp}
                  />
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>

        {/* TODO: Add more status message like error */}
        {isLoading && <div className="status-message">Scanning...</div>}
      </div>

      <InputDevice onScan={handleScan} />
    </div>
  );
}

export default App;
