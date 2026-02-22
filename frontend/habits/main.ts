import m from "mithril";

import "./habits.css";

let today = new Date();

function iso8601(d: Date): string {
  const mm = (d.getMonth() + 1 + "").padStart(2, "0");
  const dd = (d.getDate() + "").padStart(2, "0");
  return `${d.getFullYear()}-${mm}-${dd}`;
}

interface Habit {
  category: string;
  deprecated: boolean;
  description: string;
  name: string;
  once_a_day: boolean;
  points: number;
  time_created: string;
}

interface Category {
  name: string;
  habits: Habit[];
}

interface HabitEntry {
  date: string;
  habit: string;
  original_name: string;
  original_points: number;
  time_created: string;
}

interface State {
  loading: boolean;
  categories: Category[];
  entries: HabitEntry[];
  date: string;
  today: Date;
}

let STATE: State = {
  loading: true,
  categories: [],
  entries: [],
  date: iso8601(today),
  today,
};

function refresh(): void {
  m.request({
    method: "GET",
    url: "/api/load",
  }).then((data: any) => {
    STATE.loading = false;
    STATE.categories = data.categories;
    STATE.entries = data.entries;
    STATE.today = new Date();
  });
}

class PageView {
  oninit(): void {
    refresh();
    setInterval(refresh, 1000 * 60 * 15);
  }

  view() {
    if (STATE.loading) {
      return m("p", "Loading...");
    } else {
      return [
        m("h1", "Habits"),
        m("div.col2.card", [
          m("div", m(EntriesView)),
          m("div", m(CategoriesView)),
        ]),
      ];
    }
  }
}

function displayTime(dateTime: Date): string {
  let hours = dateTime.getHours();
  let amPm;
  if (hours > 12) {
    hours -= 12;
    amPm = "PM";
  } else if (hours === 0) {
    hours = 12;
    amPm = "AM";
  } else {
    amPm = "AM";
  }
  return (
    hours + ":" + ("" + dateTime.getMinutes()).padStart(2, "0") + " " + amPm
  );
}

class EntriesView {
  view() {
    const filteredEntries = STATE.entries.filter((entry) => {
      return entry.date === STATE.date;
    });
    filteredEntries.sort(
      (a, b) =>
        new Date(b.time_created).getTime() - new Date(a.time_created).getTime(),
    );
    return [
      m("h2", "Entries"),
      m(DateSelectView),
      m(
        "ul",
        filteredEntries.map((entry) => m("li", m(EntryView, { entry }))),
      ),
    ];
  }
}

class EntryView {
  view(vnode: m.Vnode<{ entry: any }>) {
    const entry = vnode.attrs.entry;
    return m("span.entry", [
      m("span.time", `${displayTime(new Date(entry.time_created))}: `),
      entry.habit,
      m(
        "span.trash",
        { onclick: () => this.deleteEntry(entry) },
        m.trust(TRASH_CAN_SVG),
      ),
    ]);
  }

  deleteEntry(entry: HabitEntry): void {
    m.request({
      method: "POST",
      url: "/api/delete",
      body: {
        date: entry.date,
        habit: entry.habit,
      },
    }).then(() => {
      refresh();
    });
  }
}

class DateSelectView {
  view() {
    const radios = [];
    for (let i = 0; i <= 14; i++) {
      const date = new Date(STATE.today);
      date.setDate(date.getDate() - i);
      let label;
      if (i === 0) {
        label = "today";
      } else if (i === 1) {
        label = "yesterday";
      } else {
        label = date.getMonth() + 1 + "/" + date.getDate();
      }
      radios.push(m(DateRadioView, { label, date }));
    }
    return m("div.date-select", radios);
  }
}

class DateRadioView {
  view(vnode: m.Vnode<{ date: Date; label: string }>) {
    const date = vnode.attrs.date;
    const label = vnode.attrs.label;
    const value = iso8601(date);
    return m("label", [
      m("input", {
        type: "radio",
        name: "date-radio",
        value,
        checked: value === STATE.date,
        onchange: this.onchange,
      }),
      label,
    ]);
  }

  onchange(e: InputEvent): void {
    if (e.target !== null) {
      STATE.date = (e.target as HTMLInputElement).value;
    }
  }
}

class CategoriesView {
  view() {
    return STATE.categories.map((category) => m(CategoryView, { category }));
  }
}

class CategoryView {
  view(vnode: m.Vnode<{ category: Category }>) {
    const category = vnode.attrs.category;
    return [
      m("h2", category.name),
      m(
        "ul.category",
        category.habits.map((habit) => m(HabitView, { habit })),
      ),
    ];
  }
}

function isFulfilled(habit: Habit): boolean {
  for (const entry of STATE.entries) {
    if (entry.habit === habit.name && entry.date === STATE.date) {
      return true;
    }
  }

  return false;
}

class HabitView {
  view(vnode: m.Vnode<{ habit: Habit }>) {
    const habit = vnode.attrs.habit;
    let cls =
      habit.points > 0 ? "positive" : habit.points < 0 ? "negative" : "neutral";
    let onclick;
    if (habit.once_a_day && isFulfilled(habit)) {
      cls += " fulfilled";
      onclick = null;
    } else {
      onclick = () => this.onclick(habit);
    }
    const suffix = habit.once_a_day ? " *" : "";
    return m("li", m(`button.${cls}`, { onclick }, habit.name + suffix));
  }

  onclick(habit: Habit): void {
    console.log(habit);
    m.request({
      method: "POST",
      url: "/api/create",
      body: {
        date: STATE.date,
        habit: habit.name,
        points: habit.points,
      },
    }).then(() => {
      refresh();
    });
  }
}

const TRASH_CAN_SVG = `
<svg data-v-72e3657a="" viewBox="0 0 16 16" width="1em" height="1em" focusable="false" role="img" aria-label="trash" xmlns="http://www.w3.org/2000/svg" fill="currentColor" class="bi-trash trash b-icon bi">
  <g data-v-72e3657a="">
    <path d="M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0V6z"></path><path fill-rule="evenodd" d="M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1h3.5a1 1 0 0 1 1 1v1zM4.118 4L4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z"></path>
  </g>
</svg>
`;

m.mount(document.body, PageView);
