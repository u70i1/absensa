/**
 * Format date to something like "RAB 07 JUL"
 *
 * @export
 * @param {Date} date - The date object to format
 * @returns {string} Formatted date string (e.g., "RAB 07 JUL")
 */
export function formatDate(date) {
  const days = ['MIN', 'SEN', 'SEL', 'RAB', 'KAM', 'JUM', 'SAB'];
  const months = ['JAN', 'FEB', 'MAR', 'APR', 'MEI', 'JUN', 'JUL', 'AGS', 'SEP', 'OKT', 'NOV', 'DES'];

  const dayName = days[date.getDay()];
  const dayNumber = date.getDate().toString().padStart(2, '0');
  const monthName = months[date.getMonth()];

  return `${dayName} ${dayNumber} ${monthName}`;
}
