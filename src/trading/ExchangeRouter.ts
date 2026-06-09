import { DeribitExchange } from "./DeribitExchange";
import { DeriveExchange } from "./DeriveExchange";
import { OptionsExchange } from "./OptionExchange";

const exchangeMap: Record<string, OptionsExchange> = {
  deribit: new DeribitExchange(),
  derive: new DeriveExchange(), // temporary
};

export function getExchange(name: string): OptionsExchange {
  const ex = exchangeMap[name.toLowerCase()];
  console.log(name, ex);

  if (!ex) throw new Error(`Exchange not supported: ${name}`);
  return ex;
}
