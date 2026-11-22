export function ListSkeleton() {
  return (
    <div className="dashboardContent" aria-busy="true" aria-label="正在加载">
      <div className="skeleton skeletonPageTitle" />
      <div className="skeletonCardGrid">
        {Array.from({ length: 6 }, (_, index) => <div className="skeleton skeletonListCard" key={index} />)}
      </div>
    </div>
  );
}
