import "./InputDevice.css";

import logo from "../assets/school-logo.png";
import OtpInput from "react-otp-input";
import { useEffect, useState, useRef, useCallback } from "react";
import { motion } from "framer-motion";

import Cable from "./Cable";
import { useLiveDate } from "../hooks/useLiveDate";

function useNisnScanner(onScan) {
  const [nisn, setNisn] = useState("");
  const [isScanning, setIsScanning] = useState(false);
  const containerRef = useRef(null);

  // auto submits when input reaches 10 digits
  const handleScan = useCallback(async () => {
    if (nisn.length !== 10) return;
    setNisn("");
    setIsScanning(true);
    await onScan(nisn);
    setIsScanning(false);
  }, [nisn, onScan]);

  useEffect(() => {
    if (nisn.length === 10) {
      handleScan();
    }
  }, [nisn, handleScan]);

  useEffect(() => {
    if (!isScanning) {
      const firstInput = containerRef.current?.querySelector("input");
      firstInput?.focus();
    }
  }, [isScanning]);

  return { nisn, setNisn, isScanning, containerRef };
}

function InputDevice({ onScan }) {
  const { date, time } = useLiveDate();
  const { nisn, setNisn, isScanning, containerRef } = useNisnScanner(onScan);

  return (
    <div className="device-container">
      <Cable />
      <div className="input-device">
        <div className="device-header">
          <img src={logo} alt="" className="device-logo" />
          <p className="device-title">
            rapture high school of art · attendance terminal
          </p>
        </div>

        <div className="input-panel">
          <div className="panel-clock">
            <span className="time">{time}</span>
            <span className="date">{date}</span>
          </div>
          <label className="panel-label">NISN</label>
          <div
            className="scanning-label"
            style={{ display: isScanning ? "flex" : "none" }}
          >
            <p>SCANNING...</p>
          </div>
          <div
            className="input-boxes"
            ref={containerRef}
            style={{ display: isScanning ? "none" : "block" }}
          >
            <OtpInput
              containerStyle={{
                display: "flex",
                justifyContent: "space-between",
                padding: "0px",

                height: "21px",
                width: "320px",
              }}
              value={nisn}
              onChange={setNisn}
              numInputs={10}
              shouldAutoFocus={true}
              renderInput={(props) => <input {...props} className="digit" />}
            />{" "}
          </div>
        </div>
        <div className="device-hole-container">
          <div className="device-hole"></div>
          <div className="device-hole"></div>
          <div className="device-hole"></div>
          <div className="device-hole"></div>
        </div>
      </div>
    </div>
  );
}

export default InputDevice;
