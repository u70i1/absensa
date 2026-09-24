import { transform, translateAxis } from "framer-motion";
import "./StudentCard.css";
import { motion, AnimatePresence } from "framer-motion";

function StudentCard({ name, nisn, time, keyId }) {
  return (
    <div className="student-card">
      <img
        className="card-img"
        src={`http://localhost:8000/photos/${nisn}.webp`}
        alt={nisn}
      />
      <div className="id-container">
        <h2 className="student-name">{name}</h2>
        <h3 className="student-nisn">{nisn}</h3>
      </div>
      <div className="time">{time}</div>
    </div>
  );
}

export default StudentCard;
