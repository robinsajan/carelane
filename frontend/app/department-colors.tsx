'use client';

export const DEPARTMENT_COLORS = [
  ['Blue', '#DBEAFE'], ['Mint', '#D1FAE5'], ['Lavender', '#EDE9FE'],
  ['Rose', '#FCE7F3'], ['Peach', '#FFEDD5'], ['Butter', '#FEF3C7'],
  ['Aqua', '#CFFAFE'], ['Slate', '#E2E8F0'],
] as const;
export const DEFAULT_DEPARTMENT_COLOR = DEPARTMENT_COLORS[0][1];

export function departmentColor(color?:string) {
  return DEPARTMENT_COLORS.find(([,value])=>value===color)?.[1] || DEFAULT_DEPARTMENT_COLOR;
}

export function DepartmentBadge({name,color}:{name:string;color?:string}) {
  const background = departmentColor(color);
  return <span className="department-badge" style={{backgroundColor:background}}>{name || 'Department'}</span>;
}

export function DepartmentColorPicker({value,onChange}:{value:string;onChange:(color:string)=>void}) {
  return <fieldset className="department-color-field"><legend>Department colour</legend>
    <p>Doctors inherit this colour in settings and OPD queues.</p>
    <div className="department-color-options">{DEPARTMENT_COLORS.map(([name,color])=><label key={color} className="department-color-option" style={{backgroundColor:color}}>
      <input type="radio" name="department-color" value={color} checked={value===color} onChange={()=>onChange(color)}/><span>{name}</span>
    </label>)}</div>
  </fieldset>;
}
