function Cable() {
  return (
    <svg
      className="cable"
      width="341"
      height="488"
      viewBox="0 0 341 488"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <g filter="url(#filter0_di_29_279)">
        <path
          d="M207.958 476C216.844 415.508 354.994 362 320.603 318C286.211 274 168.084 318 180.046 224C192.008 130 241.353 153 219.422 109.5C197.491 66 27.0288 109.5 37.4958 50.5C47.9627 -8.49999 9.08539 -7.49999 9.08539 -7.49999"
          stroke="black"
          strokeWidth="7"
        />
      </g>
      <defs>
        <filter
          id="filter0_di_29_279"
          x="0"
          y="-20.0011"
          width="340.59"
          height="507.51"
          filterUnits="userSpaceOnUse"
          colorInterpolationFilters="sRGB"
        >
          <feFlood floodOpacity="0" result="BackgroundImageFix" />
          <feColorMatrix
            in="SourceAlpha"
            type="matrix"
            values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 127 0"
            result="hardAlpha"
          />
          <feOffset dx="1" dy="1" />
          <feGaussianBlur stdDeviation="5" />
          <feComposite in2="hardAlpha" operator="out" />
          <feColorMatrix
            type="matrix"
            values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0.25 0"
          />
          <feBlend
            mode="normal"
            in2="BackgroundImageFix"
            result="effect1_dropShadow_29_279"
          />
          <feBlend
            mode="normal"
            in="SourceGraphic"
            in2="effect1_dropShadow_29_279"
            result="shape"
          />
          <feColorMatrix
            in="SourceAlpha"
            type="matrix"
            values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 127 0"
            result="hardAlpha"
          />
          <feOffset />
          <feGaussianBlur stdDeviation="2.5" />
          <feComposite in2="hardAlpha" operator="arithmetic" k2="-1" k3="1" />
          <feColorMatrix
            type="matrix"
            values="0 0 0 0 1 0 0 0 0 1 0 0 0 0 1 0 0 0 0.75 0"
          />
          <feBlend
            mode="normal"
            in2="shape"
            result="effect2_innerShadow_29_279"
          />
        </filter>
      </defs>
    </svg>
  );
}

export default Cable;
