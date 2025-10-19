import prisma from "@/lib/prisma";

export default async function Home() {
  const data = await prisma.history.findMany();

  // const triggerRun = async () => {
  //   await fetch("/api/trigger/run", {
  //     method: "POST",
  //     headers: {
  //       "Content-Type": "application/json",
  //     },
  //     body: JSON.stringify({}),
  //   });
  // };

  return (
    <div>
      data will be here:
      <div>{JSON.stringify(data)}</div>
      <form action={() => {
        
      }} method="POST">
        <button type="submit">Trigger manually</button>
      </form>
    </div>
  );
}
