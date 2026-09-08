import { processPayment } from "./payment";

class Gateway {
  process(): boolean {
    return true;
  }
}

export function checkout(): boolean {
  const gateway = new Gateway();
  gateway.process();
  return processPayment();
}
